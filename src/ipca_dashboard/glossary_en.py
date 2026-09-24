"""English display copy with the original analytical lookup keys preserved."""
import unicodedata

CARD_TERMS = {
    "IPCA m/m": "Monthly inflation: the average change in prices during the reference month compared with the previous month.",
    "IPCA 12m": "Cumulative inflation over the last 12 months, a common measure of the annual inflation rate.",
    "IPCA 3M average": "The average monthly inflation rate over the last three months. It smooths short-term fluctuations. NSA means not seasonally adjusted.",
    "Core mean, 3M average": "Three-month average of core inflation measures, which remove or smooth volatile prices to reveal underlying inflation.",
    "Diffusion 3M average": "Three-month average share of basket items whose prices increased. Higher diffusion means price increases are more widespread.",
    "IPCA 3M annualized SA": "The compounded change over three months, annualized after STL seasonal adjustment. The latest seasonal factor is an estimate and may be revised.",
    "Active alerts": "Number of attention signals triggered by explicit rules this month, such as high core inflation or broad price pressure. They are not forecasts.",
}
CONCEPTS = {
    "inflacao": "Inflation (IPCA): Brazil's official consumer price index, measured by IBGE from a basket of goods and services.",
    "variacao": "Price change (%): the monthly change in a group or item's average price, as reported by IBGE.",
    "contribuicao": "Contribution (percentage points): an item's impact on headline monthly inflation, calculated as price change × basket weight ÷ 100.",
    "peso": "Weight (%): a group or item's share of the IPCA basket. A larger weight means a price change has more impact on the headline index.",
    "nucleos": "Core inflation measures exclude or smooth volatile prices to identify the underlying trend, reducing the noise from temporary shocks.",
    "difusao": "Diffusion: the percentage of basket items with rising prices. Higher diffusion means inflation is spread across more items.",
    "mm3m": "3M average (MM3M in the source data): a three-month moving average that smooths individual monthly fluctuations.",
    "nsa": "NSA: not seasonally adjusted. Regular seasonal effects remain in the data; the STL-adjusted series is labeled SA.",
    "ajuste sazonal": "Seasonal adjustment (SA) removes recurring calendar effects using STL. The most recent estimate can be revised. This is the project's calculation, not an official IBGE/BCB series.",
    "regime": "Inflation regime: a rule-based label combining inflation's level and breadth against historical data since 2012. It is calculated deterministically, not by AI.",
    "alertas": "Alerts are triggered by explicit thresholds. They identify conditions that merit attention; they are neither recommendations nor forecasts.",
}
REGIME_LABELS = {
    "Pressão disseminada": "Broad-based pressure",
    "Desinflação disseminada": "Broad-based disinflation",
    "Desinflação frágil": "Fragile disinflation",
    "Choque localizado": "Localized shock",
    "Quadro misto": "Mixed picture",
    "Dados insuficientes": "Insufficient data",
}
REGIME_TERMS = {
    "Pressão disseminada": "Broad-based pressure: rising prices are spread across most items rather than concentrated in a few.",
    "Desinflação disseminada": "Broad-based disinflation: the headline and breadth of price increases point to easing inflation pressure.",
    "Desinflação frágil": "Fragile disinflation: headline inflation has eased, but price increases remain widespread.",
    "Choque localizado": "Localized shock: inflation increased, but the pressure is concentrated in a small number of items.",
    "Quadro misto": "Mixed picture: the indicators do not point consistently in one direction.",
    "Dados insuficientes": "Insufficient data: the available information does not support a reliable regime classification.",
}
CORE_TERMS = {
    "EX0": "EX0: an exclusion-based core measure that removes volatile components, including food at home and energy.",
    "EX1": "EX1: an exclusion-based core measure using an alternative set of volatile components.",
    "EX2": "EX2: an exclusion-based core measure that removes food at home, fuels and other volatile components.",
    "EX3": "EX3: an exclusion-based core measure that removes food at home and selected energy components.",
    "EX_FE": "EX-FE: a core measure excluding food and energy, which are particularly exposed to temporary shocks.",
    "DP": "DP (double weighting): gives less weight to more volatile items instead of removing them.",
    "MA": "MA (trimmed mean): excludes the largest and smallest monthly price changes and averages the middle of the distribution.",
    "MS": "MS (smoothed trimmed mean): also smooths items whose prices change infrequently.",
    "P55": "P55: the price change at the 55th percentile of the distribution, a robust measure of central tendency.",
}
SEVERITY_PT = {"critical": "critical", "high": "high", "medium": "medium", "low": "low", "info": "informational"}
METRIC_LABELS = {
    "mom": "monthly (m/m)",
    "rolling_12m": "over 12 months",
    "moving_average_3m": "3-month average (NSA)",
    "three_month_saar": "3-month annualized (NSA, experimental)",
    "mom_sa": "monthly, seasonally adjusted (SA)",
    "annualized_3m_sa": "3-month annualized, seasonally adjusted (SA)",
}


def metric_label(key: str) -> str:
    return METRIC_LABELS.get(key, key)


def _normalize(key: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', key) if not unicodedata.combining(c)).lower().strip()


_LOOKUP = {_normalize(k): v for k, v in {**CARD_TERMS, **CONCEPTS, **REGIME_TERMS, **CORE_TERMS}.items()}


def describe(key: str) -> str:
    return _LOOKUP.get(_normalize(key), '')
