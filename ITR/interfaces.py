from __future__ import annotations

import json
import numpy as np
import pandas as pd

from operator import add
from enum import Enum
from typing import Optional, Dict, List, Literal, Union
from typing import TYPE_CHECKING, Callable
from pydantic_core import CoreSchema
from pydantic import BaseModel, ConfigDict, GetJsonSchemaHandler, model_validator, field_validator, ValidationError
from pydantic.json_schema import JsonSchemaValue

import ITR

from ITR.data.osc_units import ureg, Q_, M_, PA_, \
    BenchmarkMetric, BenchmarkQuantity, ProductionMetric, ProductionQuantity, EmissionsMetric, EmissionsQuantity, EI_Metric, EI_Quantity, \
    MonetaryQuantity, Quantity_type
from ITR.configs import ProjectionControls, LoggingConfig

import logging
logger = logging.getLogger(__name__)
LoggingConfig.add_config_to_logger(logger)

import pint
from pint.errors import DimensionalityError
from pint_pandas import PintType
from pint_pandas.pint_array import PintSeriesAccessor

class SortableEnum(Enum):
    def __str__(self):
        return self.name

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            order = list(self.__class__)
            return order.index(self) >= order.index(other)
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            order = list(self.__class__)
            return order.index(self) > order.index(other)
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            order = list(self.__class__)
            return order.index(self) <= order.index(other)
        return NotImplemented

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            order = list(self.__class__)
            return order.index(self) < order.index(other)
        return NotImplemented


class EScope(SortableEnum):
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S1S2 = "S1+S2"
    S1S2S3 = "S1+S2+S3"
    AnyScope = 'AnyScope'

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    @classmethod
    def get_scopes(cls) -> List[str]:
        """
        Get a list of all scopes.
        :return: A list of EScope string values
        """
        return ['S1', 'S2', 'S3', 'S1S2', 'S1S2S3']

    @classmethod
    def get_result_scopes(cls) -> List['EScope']:
        """
        Get a list of scopes that should be calculated if the user leaves it open.

        :return: A list of EScope objects
        """
        # FIXME: Should this also contain cls.S2 or no?
        return [cls.S1, cls.S1S2, cls.S3, cls.S1S2S3]


class ETimeFrames(SortableEnum):
    """
    TODO: add support for multiple timeframes. Long currently corresponds to 2050.
    """
    SHORT = "short"
    MID = "mid"
    LONG = "long"


class ECarbonBudgetScenario(Enum):
    P25 = "25 percentile"
    P75 = "75 percentile"
    MEAN = "Average"


class EScoreResultType(Enum):
    DEFAULT = "Default"
    TRAJECTORY_ONLY = "Trajectory only"
    TARGET_ONLY = "Target only"
    COMPLETE = "Complete"

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    @classmethod
    def get_result_types(cls) -> List[str]:
        """
        Get a list of all result types, ordered by priority (first << last priority).
        :return: A list of the EScoreResultType values
        """
        return [EScoreResultType.DEFAULT, EScoreResultType.TRAJECTORY_ONLY, EScoreResultType.TARGET_ONLY, EScoreResultType.COMPLETE]


class AggregationContribution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    company_name: str
    company_id: str
    temperature_score: Quantity_type('delta_degC')
    contribution_relative: Optional[Quantity_type('percent')] = None
    contribution: Optional[Quantity_type('delta_degC')] = None

    def __getitem__(self, item):
        return getattr(self, item)


class Aggregation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    score: Quantity_type('delta_degC')
    # proportion is a number from 0..1
    proportion: float
    contributions: List[AggregationContribution]

    def __getitem__(self, item):
        return getattr(self, item)


class ScoreAggregation(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    all: Aggregation
    influence_percentage: Quantity_type('percent')
    grouped: Dict[str, Aggregation]

    def __getitem__(self, item):
        return getattr(self, item)


class ScoreAggregationScopes(BaseModel):
    S1: Optional[ScoreAggregation] = None
    S2: Optional[ScoreAggregation] = None
    S1S2: Optional[ScoreAggregation]=  None
    S3: Optional[ScoreAggregation] = None
    S1S2S3: Optional[ScoreAggregation] = None

    def __getitem__(self, item):
        return getattr(self, item)


class ScoreAggregations(BaseModel):
    short: Optional[ScoreAggregationScopes] = None
    mid: Optional[ScoreAggregationScopes] = None
    long: Optional[ScoreAggregationScopes] = None

    def __getitem__(self, item):
        return getattr(self, item)


class PortfolioCompany(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    company_name: str
    company_id: str
    company_isin: Optional[str] = None
    investment_value: MonetaryQuantity
    user_fields: Optional[dict] = None


# U is Unquantified, which is presently how our benchmarks come in (production_metric comes in elsewhere)
class UProjection(BaseModel):
    year: int
    value: float

class IProjection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    year: int
    value: BenchmarkQuantity


class IBenchmark(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    sector: str
    region: str
    benchmark_metric: BenchmarkMetric
    projections_nounits: Optional[List[UProjection]] = None
    projections: Optional[List[IProjection]] = None
    base_year_production: Optional[ProductionQuantity] = None  # FIXME: applies only to production benchmarks

    def __init__(self, benchmark_metric, projections_nounits=None, projections=None,
                 base_year_production=None, *args, **kwargs):
        # FIXME: Probably want to define `target_end_year` to be 2051, not 2050...
        super().__init__(benchmark_metric=benchmark_metric,
                         projections_nounits=projections_nounits,
                         projections=projections,
                         base_year_production=base_year_production,
                         *args, **kwargs)
        # Sadly we need to build the full projection range before cutting it down to size...
        # ...until Tiemann learns the bi-valence of dict and Model parameters
        if self.projections_nounits:
            if self.projections:
                # Check if we've already seen/processed these exact projections
                changed_projections = [p for p in self.projections if not any([n for n in self.projections_nounits if n.year==p.year and n.value==p.value.m])]
                if changed_projections:
                    raise ValueError
                return
            self.projections = [IProjection(year=p.year, value=BenchmarkQuantity(Q_(p.value, benchmark_metric))) for p in self.projections_nounits
                                if p.year in range(ProjectionControls.BASE_YEAR,
                                                   ProjectionControls.TARGET_YEAR+1)]
        elif not self.projections:
            logger.warning(f"Empty Benchmark for sector {sector}, region {region}")

    def __getitem__(self, item):
        return getattr(self, item)


class IBenchmarks(BaseModel):
    benchmarks: List[IBenchmark]
    production_centric:bool = False

    def __getitem__(self, item):
        return getattr(self, item)


# These IProductionBenchmarkScopes and IEIBenchmarkScopes are vessels for holding initialization data
# The CompanyDataProvider methods create their own dataframes that are then used throughout

class IProductionBenchmarkScopes(BaseModel):
    AnyScope: Optional[IBenchmarks] = None
    S1: Optional[IBenchmarks] = None
    S2: Optional[IBenchmarks] = None
    S1S2: Optional[IBenchmarks] = None
    S3: Optional[IBenchmarks] = None
    S1S2S3: Optional[IBenchmarks] = None

    def __getitem__(self, item):
        return getattr(self, item)


class IEIBenchmarkScopes(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    S1: Optional[IBenchmarks] = None
    S2: Optional[IBenchmarks] = None
    S1S2: Optional[IBenchmarks] = None
    S3: Optional[IBenchmarks] = None
    S1S2S3: Optional[IBenchmarks] = None
    benchmark_temperature: Quantity_type('delta_degC')
    benchmark_global_budget: Quantity_type('Gt CO2')
    is_AFOLU_included: bool

    def __getitem__(self, item):
        return getattr(self, item)


class ICompanyEIProjection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    year: int
    value: Optional[EI_Quantity] = None

    def __getitem__(self, item):
        return getattr(self, item)

    def __eq__(self, o):
        if self.year != o.year:
            raise ValueError(f"EI Projection years not aligned for __eq__(): {self.year} vs. {o.year}")
        if ITR.isna(self.value.m) and ITR.isna(o.value.m):
            return True
        return self.value == o.value

    def add(self, o):
        if self.year != o.year:
            # breakpoint()
            raise ValueError(f"EI Projection years not aligned for add(): {self.year} vs. {o.year}")
        return ICompanyEIProjection(year=self.year,
                                    value = self.value if ITR.isna(o.value.m) else self.value + o.value.to(self.value.units))

    def min(self, o):
        if self.year != o.year:
            raise ValueError(f"EI Projection years not aligned for min(): {self.year} vs. {o.year}")
        return ICompanyEIProjection(year=self.year, value = min(self.value, o.value))

class ICompanyEIProjections(BaseModel):
    ei_metric: EI_Metric
    projections: List[ICompanyEIProjection]

    def __getitem__(self, item):
        return getattr(self, item)

    def __str__(self):
        # Work-around for https://github.com/hgrecco/pint/issues/1687
        ei_metric = ureg.parse_units(self.ei_metric)
        series = (lambda z: (idx:=z[0], values:=z[1], pd.Series(PA_(np.asarray(values), dtype=str(ei_metric)), index=idx))[-1]) \
                 (list (zip(*[(x.year, round(ITR.Q_m_as(x.value, ei_metric), 4)) for x in self.projections])) )
        return str(series)

class DF_ICompanyEIProjections(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    ei_metric: Optional[EI_Metric] = None
    projections: pd.Series

    @field_validator('projections')
    def val_projections(cls, v: pd.Series):
        if isinstance(v.pint, PintSeriesAccessor):
            return v
        raise ValidationError(f"{v} is not composed of a PintArray")

    def __init__(self, icompany_ei_projections=None, *args, **kwargs):
        projections = None
        projections_gen = None
        if icompany_ei_projections is not None:
            ei_metric = icompany_ei_projections.ei_metric
            projections_gen = icompany_ei_projections.projections
        else:
            ei_metric = kwargs['ei_metric']
            projections = kwargs['projections']
            if not isinstance(projections, pd.Series):
                projections_gen = projections
                projections = None
        if projections_gen is not None:
            # Work-around for https://github.com/hgrecco/pint/issues/1687
            ei_metric = ureg.parse_units(ei_metric)
            years, values = list( map(list, zip(*[(x['year'], np.nan if x['value'] is None else ITR.Q_m_as(x['value'], ei_metric, inplace=True))
                                                  for x in projections_gen])) )
            projections = pd.Series(PA_(np.asarray(values), dtype=str(ei_metric)), index=pd.Index(years, name='year'), name='value')
        super().__init__(ei_metric=str(ei_metric), projections=projections)


class ICompanyEIProjectionsScopes(BaseModel):
    S1: Optional[DF_ICompanyEIProjections] = None
    S2: Optional[DF_ICompanyEIProjections] = None
    S1S2: Optional[DF_ICompanyEIProjections] = None
    S3: Optional[DF_ICompanyEIProjections] = None
    S1S2S3: Optional[DF_ICompanyEIProjections] = None

    def __init__(self, *args, **kwargs):
        # We don't validate anything in the first step because incoming parameters are the wild west
        # (dict, ICompanyEIProjections, pd.Series)
        super().__init__()
            
        for k, v in kwargs.items():
            if isinstance(v, dict):
                setattr(self, k, DF_ICompanyEIProjections(ei_metric=EI_Metric(v['ei_metric']), projections=v['projections']))
            elif isinstance(v, ICompanyEIProjections):
                setattr(self, k, DF_ICompanyEIProjections(icompany_ei_projections=v))
            elif isinstance(v, pd.Series):
                ei_metric = EI_Metric(str(v.dtype))
                if ei_metric.startswith('pint['):
                    ei_metric = ei_metric[5:-1]
                setattr(self, k, DF_ICompanyEIProjections(ei_metric=ei_metric, projections=v))
            elif isinstance(v, DF_ICompanyEIProjections) or v is None:
                setattr(self, k, v)
            else:
                # breakpoint()
                assert False
            # We could do a post-hoc validation here...

    def __getitem__(self, item):
        return getattr(self, item)

    def __str__(self):
        dict_items = {scope: getattr(self, scope).projections
                      for scope in ['S1', 'S2', 'S1S2', 'S3', 'S1S2S3']
                      if getattr(self, scope) is not None}
        return str(pd.DataFrame.from_dict(dict_items))


class IProductionRealization(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    year: int
    value: Optional[ProductionQuantity] = None


class IEmissionRealization(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    year: int
    value: Optional[EmissionsQuantity] = None

    def __getitem__(self, item):
        return getattr(self, item)

    def __eq__(self, o):
        assert self.year==o.year
        if ITR.isna(self.value.m) and ITR.isna(o.value.m):
            return True
        return self.value == o.value

    def add(self, o):
        assert self.year==o.year
        return IEmissionRealization(year=self.year,
                                    value = self.value if ITR.isna(o.value.m) else self.value + o.value.to(self.value.units))


class IHistoricEmissionsScopes(BaseModel):
    S1: List[IEmissionRealization]
    S2: List[IEmissionRealization]
    S1S2: List[IEmissionRealization]
    S3: List[IEmissionRealization]
    S1S2S3: List[IEmissionRealization]

    def __getitem__(self, item):
        return getattr(self, item)

    def __str__(self):
        dict_items = {scope: (lambda z: (idx:=z[0], values:=z[1], pd.Series(PA_(np.asarray(values), dtype="Mt CO2e"), index=idx))[-1])
                             (list(zip(*[(x.year, round(x.value.to('Mt CO2e').m, 4)) for x in getattr(self, scope)])))
                      for scope in ['S1', 'S2', 'S1S2', 'S3', 'S1S2S3']
                      if getattr(self, scope) is not None}
        return str(pd.DataFrame.from_dict(dict_items))

class IEIRealization(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    year: int
    value: Optional[EI_Quantity] = None

    def __getitem__(self, item):
        return getattr(self, item)

    def __eq__(self, o):
        assert self.year==o.year
        if ITR.isna(self.value.m) and ITR.isna(o.value.m):
            return True
        return self.value == o.value

    def add(self, o):
        assert self.year==o.year
        return IEIRealization(year=self.year,
                              value = self.value if ITR.isna(o.value.m) else self.value + o.value.to(self.value.units))


class IHistoricEIScopes(BaseModel):
    S1: List[IEIRealization]
    S2: List[IEIRealization]
    S1S2: List[IEIRealization]
    S3: List[IEIRealization]
    S1S2S3: List[IEIRealization]

    def __getitem__(self, item):
        return getattr(self, item)

    def __str__(self):
        dict_items = {scope: (lambda z: (idx:=z[0], values:=z[1], pd.Series(PA_(np.asarray(values), dtype=ei_metric), index=idx))[-1])
                             (list(zip(*[(x.year, round(x.value.to(ei_metric).m, 4)) for x in getattr(self, scope)])))
                      for scope in ['S1', 'S2', 'S1S2', 'S3', 'S1S2S3']
                      # Work-around for https://github.com/hgrecco/pint/issues/1687
                      for ei_metric in [ str(ureg.parse_units(getattr(self, scope).ei_metric)) ]
                      if getattr(self, scope) is not None}
        return str(pd.DataFrame.from_dict(dict_items))

class IHistoricData(BaseModel):
    productions: Optional[List[IProductionRealization]] = None
    emissions: Optional[IHistoricEmissionsScopes] = None
    emissions_intensities: Optional[IHistoricEIScopes] = None


class ITargetData(BaseModel):
    netzero_year: Optional[int] = None
    target_type: Union[Literal['intensity'], Literal['absolute'], Literal['Intensity'], Literal['Absolute']]
    target_scope: EScope
    target_start_year: Optional[int] = None
    target_base_year: int
    target_end_year: int

    target_base_year_qty: float
    target_base_year_err: Optional[float] = None
    target_base_year_unit: str
    target_reduction_pct: float # This is actually a fraction, not a percentage.  1.0 = complete reduction to zero.

    @model_validator(mode='before')
    def start_end_base_order(cls, v):
        if v['target_start_year'] < v['target_base_year']:
            raise ValueError(f"Scope {v['target_scope']}: Target start year ({v['target_start_year']}) must be equal or greater than base year {v['target_base_year']}")
        if v['target_end_year'] <= v['target_base_year']:
            raise ValueError(f"Scope {v['target_scope']}: Target end year ({v['target_end_year']}) must be greater than base year {v['target_base_year']}")
        if v['target_end_year'] <= v['target_start_year']:
            raise ValueError(f"Scope {v['target_scope']}: Target end year ({v['target_end_year']}) must be greater than start year {v['target_start_year']}")
        return v


class ICompanyData(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    company_name: str
    company_id: str

    sector: str  # TODO: make SortableEnums
    region: str  # TODO: make SortableEnums
    # TemperatureScoreConfig.CONTROLS_CONFIG.target_probability is not company-specific,
    # while target_probability in ICompanyData is company-specific
    target_probability: float = np.nan

    target_data: Optional[List[ITargetData]] = None
    historic_data: Optional[IHistoricData] = None  # IHistoric data can contain None values; need to convert to Quantified NaNs

    country: Optional[str] = None

    emissions_metric: Optional[EmissionsMetric] = None  # Typically use t CO2 for MWh/GJ and Mt CO2 for TWh/PJ
    production_metric: Optional[ProductionMetric] = None
    
    # These three instance variables match against financial data below, but are incomplete as historic_data and target_data
    base_year_production: Optional[ProductionQuantity] = None
    ghg_s1s2: Optional[EmissionsQuantity] = None
    ghg_s3: Optional[EmissionsQuantity] = None

    industry_level_1: Optional[str] = None
    industry_level_2: Optional[str] = None
    industry_level_3: Optional[str] = None
    industry_level_4: Optional[str] = None

    company_revenue: Optional[MonetaryQuantity] = None
    company_market_cap: Optional[MonetaryQuantity] = None
    company_enterprise_value: Optional[MonetaryQuantity] = None
    company_ev_plus_cash: Optional[MonetaryQuantity] = None
    company_total_assets: Optional[MonetaryQuantity] = None
    company_cash_equivalents: Optional[MonetaryQuantity] = None

    # Initialized later when we have benchmark information.  It is OK to initialize as None and fix later.
    # They will show up as {'S1S2': { 'projections': [ ... ] }}
    projected_targets: Optional[ICompanyEIProjectionsScopes] = None
    projected_intensities: Optional[ICompanyEIProjectionsScopes] = None

    # TODO: Do we want to do some sector inferencing here?
    
    def _sector_to_production_units(self, sector, region="Global"):
        sector_unit_dict = {
            'Electricity Utilities': { 'North America':'MWh', 'Global': 'GJ' },
            'Gas Utilities': { 'Global': 'PJ' },
            'Utilities': { 'Global': 'PJ' },
            'Steel': { 'Global': 't Steel' },
            'Aluminum': { 'Global': 't Aluminum' },
            'Energy': { 'Global': 'PJ' },
            'Coal': { 'Global': 't Coal' },
            'Oil': { 'Global': 'bbl/d' },
            'Gas': { 'Global': 'bcm' },
            'Oil & Gas': { 'Global': 'PJ' },
            'Autos': { 'Global': 'pkm' },
            'Trucking': { 'Global': 'tkm' },
            'Cement': { 'Global': 't Cement' },
            'Construction Buildings': { 'Global': 'billion USD' },
            'Residential Buildings': { 'Global': 'billion m**2' }, # Should it be 'built m**2' ?
            'Commercial Buildings': { 'Global': 'billion m**2' }, # Should it be 'built m**2' ?
            'Textiles': { 'Global': 'billion USD' },
            'Chemicals': { 'Global': 'billion USD' },
            'Chemicals': { 'Global': 'billion USD' },
            'Pharmaceuticals': { 'Global': 'billion USD' },
            'Ag Chem': { 'Global': 'billion USD' },
            'Consumer Products': { 'Global': 'billion USD' },
            'Fiber & Rubber': { 'Global': 'billion USD' },
            'Petrochem & Plastics': { 'Global': 'billion USD' },
        }
        units = None
        if sector_unit_dict.get(sector):
            region_unit_dict = sector_unit_dict[sector]
            if region_unit_dict.get(region):
                units = region_unit_dict[region]
            else:
                units = region_unit_dict['Global']
        else:
            raise ValueError(f"No source of production metrics for {self.company_name}")
        return units        

    def _get_base_realization_from_historic(self, realized_values: List[BaseModel], metric, base_year=None):
        valid_realizations = [rv for rv in realized_values if not ITR.isna(rv.value)]
        if not valid_realizations:
            retval = realized_values[0].model_copy()
            retval.year = None
            return retval
        valid_realizations.sort(key=lambda x:x.year, reverse=True)
        if base_year and valid_realizations[0].year != base_year:
            retval = realized_values[0].copy()
            retval.year = base_year
            # FIXME: Unless and until we accept uncertainties as input, rather than computed data, we don't need to make this a UFloat here
            retval.value = PintType(metric).na_value
            return retval
        return valid_realizations[0]

    def _normalize_historic_data(self, historic_data: IHistoricData, production_metric: ProductionMetric, emissions_metric: EmissionsMetric) -> IHistoricData:
        def _normalize(value, metric):
            if value is not None:
                if value.u==metric:
                    return value
                if ITR.isna(value):
                    return PintType(metric).na_value
                # We've pre-conditioned metric so don't need to work around https://github.com/hgrecco/pint/issues/1687
                return value.to(metric)
            return PintType(metric).na_value
        
        if historic_data is None:
            return None

        if historic_data.productions:
            # Work-around for https://github.com/hgrecco/pint/issues/1687
            production_metric = ureg.parse_units(production_metric)  # Catch things like '$'
            historic_data.productions = [IProductionRealization(year=p.year, value=_normalize(p.value, production_metric))
                                         for p in historic_data.productions]
        # Work-around for https://github.com/hgrecco/pint/issues/1687
        # emissions_metric = ureg(emissions_metric).u
        ei_metric = ureg.parse_units(f"{emissions_metric} / ({production_metric})")
        for scope_name in EScope.get_scopes():
            if historic_data.emissions:
                setattr(historic_data.emissions, scope_name, [IEmissionRealization(year=p.year, value=_normalize(p.value, emissions_metric))
                                                              for p in historic_data.emissions[scope_name]])
            if historic_data.emissions_intensities:
                setattr(historic_data.emissions_intensities, scope_name, [IEIRealization(year=p.year, value=_normalize(p.value, ei_metric))
                                                                          for p in historic_data.emissions_intensities[scope_name]])
        return historic_data

    def __init__(self, emissions_metric=None, production_metric=None, base_year_production=None, ghg_s1s2=None, ghg_s3=None,
                 target_data=None, historic_data=None, *args, **kwargs):
        super().__init__(emissions_metric=emissions_metric,
                         production_metric=production_metric,
                         base_year_production=base_year_production,
                         ghg_s1s2=ghg_s1s2, ghg_s3=ghg_s3,
                         target_data=target_data,
                         historic_data=historic_data,
                         *args, **kwargs)
        # In-bound parameters are JSON (str, int, float, dict), which are converted to models by __super__ and stored as instance variables
        if production_metric is None:
            units = self._sector_to_production_units(self.sector, self.region)
            self.production_metric = ProductionMetric(units)
            if emissions_metric is None:
                self.emissions_metric = EmissionsMetric('t CO2')
        elif emissions_metric is None:
            if str(self.production_metric) in ['TWh', 'PJ', 'Mt Steel', 'megaFe_ton', 'mmboe']:
                self.emissions_metric = EmissionsMetric('Mt CO2')
            else:
                self.emissions_metric = EmissionsMetric('t CO2')
            # TODO: Should raise a warning here

        # This is only a partial initialization
        if self.historic_data is None:
            return
        self.historic_data = self._normalize_historic_data(self.historic_data, self.production_metric, self.emissions_metric)
        base_year = None
        if self.base_year_production:
            pass
        # Right now historic_data comes in via template.py ESG data
        elif self.historic_data.productions:
            # TODO: This is a hack to get things going.
            base_realization = self._get_base_realization_from_historic(self.historic_data.productions, self.production_metric, base_year)
            base_year = base_realization.year
            self.base_year_production = base_realization.value
        else:
            logger.warning(f"missing historic data for base_year_production for {self.company_name}")
            self.base_year_production = PintType(self.production_metric).na_value
        if self.ghg_s1s2 is None and self.historic_data.emissions:
            if self.historic_data.emissions.S1S2:
                base_realization = self._get_base_realization_from_historic(self.historic_data.emissions.S1S2, self.emissions_metric, base_year)
                base_year = base_year or base_realization.year
                self.ghg_s1s2 = base_realization.value
            elif self.historic_data.emissions.S1 and self.historic_data.emissions.S2:
                base_realization_s1 = self._get_base_realization_from_historic(self.historic_data.emissions.S1, self.emissions_metric, base_year)
                base_realization_s2 = self._get_base_realization_from_historic(self.historic_data.emissions.S2, self.emissions_metric, base_year)
                base_year = base_year or base_realization_s1.year
                if base_realization_s1.value is not None and base_realization_s2.value is not None:
                    self.ghg_s1s2 = base_realization_s1.value + base_realization_s2.value
        if self.ghg_s1s2 is None and self.historic_data.emissions_intensities:
            intensity_metric = ureg.parse_units(f"({self.emissions_metric}) / ({self.production_metric})")
            if self.historic_data.emissions_intensities.S1S2:
                base_realization = self._get_base_realization_from_historic(self.historic_data.emissions_intensities.S1S2, intensity_metric, base_year)
                base_year = base_year or base_realization.year
                if base_realization.value is not None:
                    self.ghg_s1s2 = base_realization.value * self.base_year_production
            elif self.historic_data.emissions_intensities.S1 and self.historic_data.emissions_intensities.S2:
                base_realization_s1 = self._get_base_realization_from_historic(self.historic_data.emissions_intensities.S1, intensity_metric, base_year)
                base_realization_s2 = self._get_base_realization_from_historic(self.historic_data.emissions_intensities.S2, intensity_metric, base_year)
                base_year = base_year or base_realization_s1.year
                if base_realization_s1.value is not None and base_realization_s2.value is not None:
                    self.ghg_s1s2 = (base_realization_s1.value + base_realization_s2.value) * self.base_year_production
            else:
                raise ValueError(f"missing S1S2 historic intensity data for {self.company_name}")
        if self.ghg_s1s2 is None:
            raise ValueError(f"missing historic emissions or intensity data to calculate ghg_s1s2 for {self.company_name}")
        if self.ghg_s3 is None and self.historic_data.emissions and self.historic_data.emissions.S3:
            base_realization_s3 = self._get_base_realization_from_historic(self.historic_data.emissions.S3, self.emissions_metric, base_year)
            self.ghg_s3 = base_realization_s3.value
        if self.ghg_s3 is None and self.historic_data.emissions_intensities:
            if self.historic_data.emissions_intensities.S3:
                intensity_metric = ureg.parse_units(f"({self.emissions_metric}) / ({self.production_metric})")
                base_realization_s3 = self._get_base_realization_from_historic(self.historic_data.emissions_intensities.S3, intensity_metric, base_year)
                if base_realization_s3.value is not None:
                    self.ghg_s3 = base_realization_s3.value * self.base_year_production


# These aggregate terms are all derived from the benchmark being used
class ICompanyAggregates(ICompanyData):
    cumulative_budget: Optional[EmissionsQuantity] = None
    cumulative_scaled_budget: Optional[EmissionsQuantity] = None
    cumulative_trajectory: Optional[EmissionsQuantity] = None
    cumulative_target: Optional[EmissionsQuantity] = None
    benchmark_temperature: Optional[Quantity_type('delta_degC')] = None
    benchmark_global_budget: Optional[EmissionsQuantity] = None
    scope: Optional[EScope] = None

    # The first year that cumulative_projections exceeds the 2050 cumulative_budget
    trajectory_exceedance_year: Optional[int] = None
    target_exceedance_year: Optional[int] = None

    # projected_production is computed but never saved, so computed at least 2x: initialiation/projection and cumulative budget
    # projected_targets: Optional[ICompanyEIProjectionsScopes] = None
    # projected_intensities: Optional[ICompanyEIProjectionsScopes] = None

    # Custom validator here
    @field_validator('trajectory_exceedance_year', 'target_exceedance_year')
    def val_exceedance_year(cls, v):
        if isinstance(v, int):
            return v
        if pd.isna(v):
            return None
        raise ValueError(f"{v} is not compatible with Int64 dtype")

    @classmethod
    def from_ICompanyData(cls, super_instance, scope_company_data):
        '''
        Fast way to add instance variables to a pre-validated SUPER_INSTANCE
        SCOPE_COMPANY_DATA is the dictionary of the new values we want to add...for this one company
        '''
        # FIXME: Would love to know how to run these automatically...
        EmissionsQuantity(scope_company_data['cumulative_budget'])
        EmissionsQuantity(scope_company_data['cumulative_scaled_budget'])
        if not ITR.isna(scope_company_data['cumulative_trajectory']):
            EmissionsQuantity(scope_company_data['cumulative_trajectory'])
        if not ITR.isna(scope_company_data['cumulative_target']):
            EmissionsQuantity(scope_company_data['cumulative_target'])
        if not Q_(scope_company_data['benchmark_temperature']).is_compatible_with(ureg('delta_degC')):
            raise ValueError(f"benchmark temperature {scope_company_data['benchmark_temperature']} is not compatible with delta_degC")
        else:
            scope_company_data['benchmark_temperature'] = Q_(scope_company_data['benchmark_temperature'])
        EmissionsQuantity(scope_company_data['benchmark_global_budget'])
        if not isinstance(scope_company_data['scope'], EScope):
            raise ValueError(f"scope {scope_company_data['scope']} is not a valid scope")
        if not ITR.isna(scope_company_data['trajectory_exceedance_year']) and not isinstance(scope_company_data['trajectory_exceedance_year'], int):
            raise ValueError(f"scope {scope_company_data['trajectory_exceedance_year']} is not a valid trajectory exceedance year value")
        if not ITR.isna(scope_company_data['target_exceedance_year']) and not isinstance(scope_company_data['target_exceedance_year'], int):
            raise ValueError(f"scope {scope_company_data['target_exceedance_year']} is not a valid target exceedance year value")
        # ...while not re-running any validation on super_instnace
        return cls.model_construct(**scope_company_data, **super_instance.__dict__)
