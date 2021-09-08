import logging
import pandas as pd
from typing import List, Optional, Tuple, Type, Dict

from .configs import ColumnsConfig, TemperatureScoreConfig
from .interfaces import PortfolioCompany, EScope, ETimeFrames, ScoreAggregations, \
    IDataProviderCompany, TemperatureScoreControls

from .temperature_score import TemperatureScore
from .portfolio_aggregation import PortfolioAggregationMethod

from . import data

DATA_PROVIDER_MAP: Dict[str, Type[data.DataProvider]] = {
    "excel": data.ExcelProvider,
    "csv": data.CSVProvider,
}


def get_data_providers(data_providers_configs: List[dict], data_providers_input: List[str]) -> List[data.DataProvider]:
    """
    Determines which data provider and in which order should be used.

    :param data_providers_configs: A list of data provider configurations
    :param data_providers_input: A list of data provider names
    :return: a list of data providers in order.
    """
    logger = logging.getLogger(__name__)
    data_providers = []
    for data_provider_config in data_providers_configs:
        data_provider_config["class"] = DATA_PROVIDER_MAP[data_provider_config["type"]](
            **data_provider_config["parameters"])
        data_providers.append(data_provider_config)

    selected_data_providers = []
    for data_provider_name in data_providers_input:
        found = False
        for data_provider_config in data_providers:
            if data_provider_config["name"] == data_provider_name:
                selected_data_providers.append(data_provider_config["class"])
                found = True
                break
        if not found:
            logger.warning("The following data provider could not be found: {}".format(data_provider_name))

    if len(selected_data_providers) == 0:
        raise ValueError("None of the selected data providers are available. The following data providers are valid "
                         "options: " + ", ".join(data_provider["name"] for data_provider in data_providers_configs))
    return selected_data_providers


def get_company_data(data_providers: list, company_ids: List[str]) -> List[IDataProviderCompany]:
    """
    Get the company data in a waterfall method, given a list of companies and a list of data providers. This will go
    through the list of data providers and retrieve the required info until either there are no companies left or there
    are no data providers left.

    :param data_providers: A list of data providers instances
    :param company_ids: A list of company ids (ISINs)
    :return: A data frame containing the company data
    """
    company_data = []
    logger = logging.getLogger(__name__)
    for dp in data_providers:
        try:
            company_data_provider = dp.get_company_data(company_ids)
            company_data += company_data_provider
            company_ids = [company for company in company_ids
                           if company not in [c.company_id for c in company_data_provider]]
            if len(company_ids) == 0:
                break
        except NotImplementedError:
            logger.warning("{} is not available yet".format(type(dp).__name__))

    return company_data


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

    # bla
    return [PortfolioCompany.parse_obj(company) for company in df_portfolio.to_dict(orient="records")]


def get_data(data_providers: List[data.DataProvider], portfolio: List[PortfolioCompany]) -> pd.DataFrame:
    """
    Get the required data from the data provider(s) and return a 9-box grid for each company.

    :param data_providers: A list of DataProvider instances
    :param portfolio: A list of PortfolioCompany models
    :return: A data frame containing the relevant company data
    """
    df_portfolio = pd.DataFrame.from_records([_flatten_user_fields(c) for c in portfolio])
    # Look for data in all data providers:
    company_data = get_company_data(data_providers, df_portfolio["company_id"].tolist())

    if len(company_data) == 0:
        raise ValueError("None of the companies in your portfolio could be found by the data providers")

    df_company_data = pd.DataFrame.from_records([c.dict() for c in company_data])
    portfolio_data = pd.merge(left=df_company_data, right=df_portfolio.drop("company_name", axis=1), how="left",
                              on=["company_id"])

    return portfolio_data

    return pd.DataFrame.from_records([c.dict() for c in company_data])


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