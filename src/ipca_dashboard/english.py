"""English presentation helpers. Data files, metric keys and numerical values are preserved."""
import re

from ipca_dashboard.diagnostics import build_diagnostic_text
from ipca_dashboard.english_items import ITEM_LABELS
from ipca_dashboard.glossary_en import REGIME_LABELS

LEVEL_LABEL_PT = {"group": "Group", "subgroup": "Subgroup", "item": "Item", "subitem": "Subitem"}
PHRASES = {
    **ITEM_LABELS,
    **REGIME_LABELS,
    "BCB/RPM compacto": "Compact BCB/RPM set",
    "Seis núcleos": "Six core measures",
    "Conjunto amplo SGS": "Broad SGS set",
    "Usuário": "Custom set",
    "Média dos núcleos em 3 meses anualizado (NSA, experimental) acima de 5,0%. Pressão subjacente desconfortável.": "Mean core inflation above 5.0% on a 3-month annualized basis (NSA, experimental). Elevated underlying pressure.",
    "Ao menos um núcleo roda acima de 6,5% em 3 meses anualizado (NSA, experimental). Risco de persistência elevado.": "At least one core measure exceeds 6.5% on a 3-month annualized basis (NSA, experimental). Elevated persistence risk.",
    "Difusão MM3M acima do p80 histórico. Inflação disseminada.": "Three-month average diffusion above its historical 80th percentile. Broad-based inflation.",
    "Difusão MM3M acima do p90 histórico. Deterioração ampla.": "Three-month average diffusion above its historical 90th percentile. Widespread deterioration.",
    "Serviços em 3 meses anualizado (NSA, experimental) acima do ritmo de 12 meses. Sinal de aceleração.": "Three-month annualized services inflation (NSA, experimental) is above its 12-month pace, indicating acceleration.",
    "Headline pressionado com difusão baixa. Alta possivelmente concentrada.": "Elevated headline inflation with low diffusion. Price increases may be concentrated.",
    "Sem dados processados.": "No processed data.",
    "sem destaque": "no standout contribution",
    "contribuição baixista": "downward contribution",
    "menor contribuição": "lowest contribution",
    "sem leitura de núcleos suficiente": "insufficient core data",
    "leitura de curto prazo em MM3M (NSA)": "a short-term reading based on the three-month average (NSA)",
    "núcleos ainda sem janela completa": "an incomplete core observation window",
    "sem alertas ativos": "with no active alerts",
    "alerta ativo sem descrição configurada": "an active alert with no configured description",
    " alerta(s) ativo(s), incluindo: ": " active alert(s), including: ",
    "moderada": "moderate",
    "adversa": "adverse",
    "mais benigna": "more benign",
    "O IPCA de ": "IPCA in ",
    " veio em ": " was ",
    "%, acumulando ": "%, with a cumulative change of ",
    "% em 12 meses. A composição foi ": "% over 12 months. The composition was ",
    ", com destaque altista para ": ", led on the upside by ",
    " e contribuição baixista de ": " and a downward contribution from ",
    " e menor contribuição de ": " and the lowest contribution from ",
    ". A média dos núcleos avançou ": ". Mean core inflation was ",
    "% no mês e roda a ": "% for the month and ",
    "% em MM3M (NSA), sinalizando ": "% on a three-month average basis (NSA), indicating ",
    ". A difusão ficou em ": ". Diffusion was ",
    "% em MM3M), ": "% on a three-month average basis), ",
    "com ": "with ",
}
_PATTERN = re.compile("|".join(re.escape(k) for k in sorted(PHRASES, key=len, reverse=True)))


def translate_text(value: object) -> str:
    return _PATTERN.sub(lambda match: PHRASES[match.group(0)], str(value))


def display_data(data: dict) -> dict:
    """Copy only frames with display labels; retain all keys and numeric columns."""
    result = dict(data)
    if "items" in data:
        result["items"] = data["items"].copy()
        result["items"]["item_name"] = result["items"]["item_name"].map(
            lambda value: ITEM_LABELS.get(str(value), str(value))
        )
    if "alerts" in data:
        result["alerts"] = data["alerts"].copy()
        if "message" in result["alerts"]:
            result["alerts"]["message"] = result["alerts"]["message"].map(translate_text)
    return result


def english_diagnostic(data: dict) -> str:
    diagnostic = build_diagnostic_text(data["bcb"], data["items"], data["cores"], data["alerts"])
    return translate_text(diagnostic["diagnostic"])


METHODOLOGY_EN = """
**Sources.** BCB/SGS for headline IPCA, macro aggregates, core measures and diffusion;
IBGE/SIDRA table 7060 for weights, price changes and the group → subgroup → item → subitem hierarchy.

**Monthly contribution.** `monthly_weight * monthly_price_change / 100`, in percentage points.

**Short-term momentum.** The interface uses a three-month moving average of monthly inflation,
without seasonal adjustment (NSA). `three_month_saar` remains available for audit but is an
experimental annualized NSA measure, not a seasonally adjusted annual rate.

**Seasonal adjustment (SA).** Headline and core series are adjusted with **STL**
(`statsmodels.tsa.seasonal.STL`, additive decomposition, `robust=True`):
`SA = observed − seasonal_component`. This produces `mom_sa` and `annualized_3m_sa`.
The latest seasonal factor is an estimate and can be revised. This is the project's own STL
adjustment, not official X-13ARIMA-SEATS or an IBGE/BCB statistic. It runs in the pipeline;
if the dependency is unavailable, the SA series remains empty while NSA views continue to work.

**Core measures.** Their mean is calculated from the selected set in `config/core_sets.yaml`.

**Alerts.** Explicit rules in `config/alert_rules.yaml`; the dashboard shows alerts triggered
in the latest processing run.

**Validation.** The pipeline checks duplicates, plausible ranges, availability of the default
core set, and differences between summed group contributions and headline inflation.
"""
