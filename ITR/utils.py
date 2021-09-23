import logging
import pandas as pd
from typing import List, Optional, Tuple, Type, Dict

from .configs import ColumnsConfig, TemperatureScoreConfig
from .interfaces import PortfolioCompany, EScope, ETimeFrames, ScoreAggregations, \
    ICompanyData, TemperatureScoreControls

from .temperature_score import TemperatureScore
from .portfolio_aggregation import PortfolioAggregationMethod

from . import data
from .data.data_warehouse import DataWarehouse

def _flatten_user_fields(record: PortfolioCompany):
    """
    Flatten the user fields in a portfolio company and return it as a dictionary.

    :param record: The record to flatten
    :return:
    """
    record_dict = record.dict(exclude_none=True)
    if record.user_fields is not None:
        for key, value in record_dict["user_fields"].items():
            record_dict[key] = value
        del record_dict["user_fields"]

    return record_dict


def _make_isin_map(df_portfolio: pd.DataFrame) -> dict:
    """
    Create a mapping from company_id to ISIN (required for the SBTi matching).

    :param df_portfolio: The complete portfolio
    :return: A mapping from company_id to ISIN
    """
    return {company_id: company[ColumnsConfig.COMPANY_ISIN]
            for company_id, company in df_portfolio[[ColumnsConfig.COMPANY_ID, ColumnsConfig.COMPANY_ISIN]]
                .set_index(ColumnsConfig.COMPANY_ID)
                .to_dict(orient='index').items()}


def dataframe_to_portfolio(df_portfolio: pd.DataFrame) -> List[PortfolioCompany]:
    """
    Convert a data frame to a list of portfolio company objects.

    :param df_portfolio: The data frame to parse. The column names should align with the attribute names of the
    PortfolioCompany model.
    :return: A list of portfolio companies
    """
    return [PortfolioCompany.parse_obj(company) for company in df_portfolio.to_dict(orient="records")]


def get_data(data_warehouse: DataWarehouse, portfolio: List[PortfolioCompany]) -> pd.DataFrame:
    """
    Get the required data from the data provider(s) and return a 9-box grid for each company.

    :param data_providers: A list of DataProvider instances
    :param portfolio: A list of PortfolioCompany models
    :return: A data frame containing the relevant company data
    """
    df_portfolio = pd.DataFrame.from_records([_flatten_user_fields(c) for c in portfolio])

    company_data = data_warehouse.get_company_aggregates(df_portfolio[ColumnsConfig.COMPANY_ID].to_list())

    if len(company_data) == 0:
        raise ValueError("None of the companies in your portfolio could be found by the data providers")

    df_company_data = pd.DataFrame.from_records([c.dict() for c in company_data])
    portfolio_data = pd.merge(left=df_company_data, right=df_portfolio.drop("company_name", axis=1), how="left",
                              on=["company_id"])

    return portfolio_data


def calculate(portfolio_data: pd.DataFrame, fallback_score: float, aggregation_method: PortfolioAggregationMethod,
              grouping: Optional[List[str]], time_frames: List[ETimeFrames],
              scopes: List[EScope], anonymize: bool, aggregate: bool = True,
              controls: Optional[TemperatureScoreControls] = None) -> Tuple[pd.DataFrame,
                                                                            Optional[ScoreAggregations]]:
    """
    Calculate the different parts of the temperature score (actual scores, aggregations, column distribution).

    :param portfolio_data: The portfolio data, already processed by the target validation module
    :param fallback_score: The fallback score to use while calculating the temperature score
    :param aggregation_method: The aggregation method to use
    :param time_frames: The time frames that the temperature scores should be calculated for  (None to calculate all)
    :param scopes: The scopes that the temperature scores should be calculated for (None to calculate all)
    :param grouping: The names of the columns to group on
    :param anonymize: Whether to anonymize the resulting data set or not
    :param aggregate: Whether to aggregate the scores or not
    :return: The scores, the aggregations and the column distribution (if a
    """

    config = TemperatureScoreConfig
    if controls:
        TemperatureScoreConfig.CONTROLS_CONFIG = controls
    ts = TemperatureScore(time_frames=time_frames, scopes=scopes, fallback_score=fallback_score,
                          grouping=grouping, aggregation_method=aggregation_method, config=config)

    scores = ts.calculate(portfolio_data)
    aggregations = None
    if aggregate:
        aggregations = ts.aggregate_scores(scores)

    if anonymize:
        scores = ts.anonymize_data_dump(scores)

    return scores, aggregations