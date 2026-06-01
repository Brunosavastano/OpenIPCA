"""Tool API: the deterministic boundary the AI layer sees the world through.

Each tool reads the processed frames and returns Evidence items (value +
evidence_id + metadata) — never a bare number (spec_V3 §3.2). The model can only
cite what these tools emit. The same tools serve the v0.1 grounded brief and the
v0.2 agentic Ask-the-IPCA, unchanged.

All tools operate on the latest available month and are pure functions of their
DataFrame inputs (no network, no global state).
"""

from __future__ import annotations

import pandas as pd

from ipca_dashboard.ai.evidence import Evidence
from ipca_dashboard.regime import classify_inflation_regime

SOURCE_SGS = "BCB/SGS"
SOURCE_SIDRA = "IBGE/SIDRA 7060"


def _latest_row(bcb: pd.DataFrame, name: str) -> pd.Series | None:
    subset = bcb[bcb["series_short_name"] == name].sort_values("date")
    return subset.iloc[-1] if not subset.empty else None


def _row_at(bcb: pd.DataFrame, name: str, date: pd.Timestamp) -> pd.Series | None:
    subset = bcb[
        (bcb["series_short_name"] == name) & (pd.to_datetime(bcb["date"]) == date)
    ].sort_values("date")
    return subset.iloc[-1] if not subset.empty else None


def _month(row: pd.Series) -> str:
    return pd.to_datetime(row["date"]).strftime("%Y-%m")


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value == value else None


def get_headline(bcb: pd.DataFrame) -> list[Evidence]:
    """IPCA headline: m/m, 12m, MM3M (NSA — no SAAR; spec_V3 §4.4)."""
    row = _latest_row(bcb, "IPCA")
    if row is None:
        return []
    month = _month(row)
    return [
        Evidence("ev_headline_mom", "IPCA m/m", _num(row.get("mom")), "%", month, SOURCE_SGS),
        Evidence(
            "ev_headline_12m", "IPCA 12m", _num(row.get("rolling_12m")), "%", month, SOURCE_SGS
        ),
        Evidence(
            "ev_headline_mm3",
            "IPCA MM3M (NSA)",
            _num(row.get("moving_average_3m")),
            "%",
            month,
            SOURCE_SGS,
            "média móvel 3m da variação m/m, sem ajuste sazonal",
        ),
        Evidence(
            "ev_headline_percentile",
            "IPCA m/m percentil",
            _num(row.get("percentile_since_2012")),
            "percentile",
            month,
            SOURCE_SGS,
        ),
    ]


def get_diffusion(bcb: pd.DataFrame) -> list[Evidence]:
    """Official BCB diffusion: level, MM3M, MM3M percentile."""
    row = _latest_row(bcb, "Difusao")
    if row is None:
        return []
    month = _month(row)
    return [
        Evidence(
            "ev_diffusion_mom",
            "Difusão m/m",
            _num(row.get("mom")),
            "% de subitens",
            month,
            SOURCE_SGS,
        ),
        Evidence(
            "ev_diffusion_mm3",
            "Difusão MM3M",
            _num(row.get("moving_average_3m")),
            "% de subitens",
            month,
            SOURCE_SGS,
        ),
        Evidence(
            "ev_diffusion_mm3_percentile",
            "Difusão MM3M percentil",
            _num(row.get("moving_average_3m_percentile")),
            "percentile",
            month,
            SOURCE_SGS,
        ),
    ]


def get_cores(
    bcb: pd.DataFrame, core_metrics: pd.DataFrame, core_set: str = "bcb_compact"
) -> list[Evidence]:
    """Core mean for the preset: m/m and MM3M, with completeness."""
    if core_metrics.empty:
        return []
    latest_date = pd.to_datetime(core_metrics["date"]).max()
    mean = core_metrics[
        (core_metrics["core_set_name"] == core_set)
        & (core_metrics["core_name"].isin(["Media", "Média"]))
        & (core_metrics["date"] == latest_date)
    ]
    if mean.empty:
        return []
    row = mean.iloc[0]
    month = pd.to_datetime(latest_date).strftime("%Y-%m")
    complete = row.get("is_complete", row.get("is_complete_core_set"))
    interp = "" if bool(complete) else "preset incompleto no mês"
    return [
        Evidence(
            "ev_core_mean_mom",
            f"Média núcleos m/m ({core_set})",
            _num(row.get("mom")),
            "%",
            month,
            SOURCE_SGS,
            interp,
        ),
        Evidence(
            "ev_core_mean_mm3",
            f"Média núcleos MM3M ({core_set})",
            _num(row.get("moving_average_3m")),
            "%",
            month,
            SOURCE_SGS,
            interp,
        ),
    ]


def get_contributions(ipca_items: pd.DataFrame, top_n: int = 3) -> list[Evidence]:
    """Top positive / negative group contributions for the latest month."""
    groups = ipca_items[ipca_items["level"] == "group"].dropna(subset=["contribution_mom"])
    if groups.empty:
        return []
    latest_date = pd.to_datetime(groups["date"]).max()
    latest = groups[groups["date"] == latest_date].sort_values("contribution_mom", ascending=False)
    month = pd.to_datetime(latest_date).strftime("%Y-%m")
    out: list[Evidence] = []
    for i, (_, r) in enumerate(latest.head(top_n).iterrows()):
        out.append(
            Evidence(
                f"ev_contrib_top_pos_{i}",
                f"Contribuição: {r['item_name']}",
                _num(r["contribution_mom"]),
                "p.p.",
                month,
                SOURCE_SIDRA,
                "pressão altista",
            )
        )
    for i, (_, r) in enumerate(latest.tail(top_n).iloc[::-1].iterrows()):
        out.append(
            Evidence(
                f"ev_contrib_top_neg_{i}",
                f"Contribuição: {r['item_name']}",
                _num(r["contribution_mom"]),
                "p.p.",
                month,
                SOURCE_SIDRA,
                "alívio / menor pressão",
            )
        )
    return out


def get_alerts(alerts: pd.DataFrame) -> list[Evidence]:
    """Active alerts for the latest processing as evidence items."""
    if alerts.empty:
        return []
    out: list[Evidence] = []
    for i, (_, r) in enumerate(alerts.iterrows()):
        month = str(r.get("reference_month", ""))
        out.append(
            Evidence(
                f"ev_alert_{i}",
                f"Alerta: {r.get('alert_id', 'desconhecido')}",
                _num(r.get("value")),
                "",
                month,
                SOURCE_SGS,
                str(r.get("severity", "")),
            )
        )
    return out


def get_regime(bcb: pd.DataFrame) -> list[Evidence]:
    """The deterministic regime label (CP5) as a citable evidence item."""
    if bcb.empty:
        return []
    latest_date = pd.to_datetime(bcb["date"]).max()
    head = _row_at(bcb, "IPCA", latest_date)
    diff = _row_at(bcb, "Difusao", latest_date)
    if head is None or diff is None:
        return []
    # Reuse the global-latest-month context contract from CP5 via the classifier.
    context = {
        "headline_percentile": _num(head.get("percentile_since_2012")),
        "diffusion_mm3_percentile": _num(diff.get("moving_average_3m_percentile")),
        "evidence_ids": ["ev_headline_percentile", "ev_diffusion_mm3_percentile"],
    }
    result = classify_inflation_regime(context)
    month = _month(head)
    return [
        Evidence(
            "ev_regime",
            "Regime inflacionário",
            result.label_pt,
            "label",
            month,
            "OpenIPCA (determinístico)",
            result.rule_id,
        )
    ]


def build_evidence_table(
    bcb: pd.DataFrame,
    ipca_items: pd.DataFrame,
    core_metrics: pd.DataFrame,
    alerts: pd.DataFrame,
    core_set: str = "bcb_compact",
) -> list[Evidence]:
    """Concatenate every tool's output: the full set of citable facts."""
    table: list[Evidence] = []
    table += get_headline(bcb)
    table += get_diffusion(bcb)
    table += get_cores(bcb, core_metrics, core_set)
    table += get_contributions(ipca_items)
    table += get_alerts(alerts)
    table += get_regime(bcb)
    return table
