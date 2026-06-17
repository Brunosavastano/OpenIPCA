"""Tool API: the deterministic boundary the AI layer sees the world through.

Each tool reads the processed frames and returns Evidence items (value +
evidence_id + metadata) — never a bare number (spec_V3 §3.2). The model can only
cite what these tools emit. The same tools serve the v0.1 grounded brief and the
v0.2 agentic Ask-the-IPCA, unchanged.

All tools operate on the latest available month and are pure functions of their
DataFrame inputs (no network, no global state).
"""

from __future__ import annotations

import re
import unicodedata

import pandas as pd

from ipca_dashboard.ai.evidence import Evidence
from ipca_dashboard.regime import classify_inflation_regime

SOURCE_SGS = "BCB/SGS"
SOURCE_SIDRA = "IBGE/SIDRA 7060"
# Seasonal adjustment is computed by OpenIPCA (STL over the BCB/SGS series), not an
# official BCB/IBGE figure — the distinct source keeps that honest in every citation.
SOURCE_STL = "OpenIPCA (STL sobre BCB/SGS)"


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
    # Round at the source (2 decimals) so every evidence value is clean: the model
    # copies "4.39", not "4.39171967147336", and the guardrail (_matches, 0.005
    # tolerance) stays compatible. This is the single chokepoint for all evidence.
    return round(float(value), 2) if isinstance(value, (int, float)) and value == value else None


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
            "percentil da história desde 2012 (janela expansiva, midrank)",
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
            "percentil da história desde 2012 (janela expansiva, midrank)",
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


def get_seasonal_adjustment(
    bcb: pd.DataFrame, core_metrics: pd.DataFrame, core_set: str = "bcb_compact"
) -> list[Evidence]:
    """Seasonally adjusted momentum (STL): headline + core mean, 3m annualized.

    Q&A ONLY — deliberately kept OUT of build_evidence_table (the brief path). The
    brief is the fragile monthly artifact and stays lean (same discipline as the
    reference corpus); SA momentum is citable in the live Q&A, where "is inflation
    accelerating?" questions land. value is None when the column is absent (older
    parquet) — the row still documents the metric and its STL provenance.
    """
    out: list[Evidence] = []
    row = _latest_row(bcb, "IPCA")
    if row is not None:
        out.append(
            Evidence(
                "ev_headline_saar_sa",
                "IPCA 3m anualizado (SA)",
                _num(row.get("annualized_3m_sa")),
                "% a.a.",
                _month(row),
                SOURCE_STL,
                "momentum dessazonalizado (STL), 3m anualizado; o fator sazonal do mês "
                "mais recente é estimativa e revisa quando entram novos dados",
            )
        )
    if not core_metrics.empty:
        latest_date = pd.to_datetime(core_metrics["date"]).max()
        mean = core_metrics[
            (core_metrics["core_set_name"] == core_set)
            & (core_metrics["core_name"].isin(["Media", "Média"]))
            & (core_metrics["date"] == latest_date)
        ]
        if not mean.empty:
            crow = mean.iloc[0]
            out.append(
                Evidence(
                    "ev_core_mean_saar_sa",
                    f"Média núcleos 3m anualizado SA ({core_set})",
                    _num(crow.get("annualized_3m_sa")),
                    "% a.a.",
                    pd.to_datetime(latest_date).strftime("%Y-%m"),
                    SOURCE_STL,
                    "momentum dessazonalizado (STL); fator sazonal recente revisa",
                )
            )
    return out


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


def _normalize(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", stripped).strip()


# Levels a user might name in a question. "headline" is excluded on purpose: it's the
# index itself (weight 100), and "IPCA" would otherwise match every "...no IPCA?".
_WEIGHT_LEVELS = ("group", "subgroup", "item", "subitem")


def _match_named_items(question: str, ipca_items: pd.DataFrame, max_items: int) -> list[pd.Series]:
    """Latest-month IPCA item rows NAMED in the question — the shared matcher.

    Word-bounded (so "Sal" doesn't fire on "salário"), longest-name-first (so
    "passagem aérea" wins over a bare "passagem"), deduped by name and capped by
    weight (the most material items). Excludes the headline level. Never raises;
    returns [] on bad/empty/short-of-columns input. Each returned row carries the
    coerced reference date in "_date". Shared by the Q&A item tools (weights, changes).
    """
    required = {"date", "level", "item_name", "classification_code", "weight"}
    if not isinstance(ipca_items, pd.DataFrame) or ipca_items.empty:
        return []
    if not required.issubset(ipca_items.columns):
        return []
    q = _normalize(question)
    if not q:
        return []
    frame = ipca_items.copy()
    frame["_date"] = pd.to_datetime(frame["date"], errors="coerce")
    latest_date = frame["_date"].max()
    if pd.isna(latest_date):
        return []
    latest = frame[
        (frame["_date"] == latest_date) & (frame["level"].isin(_WEIGHT_LEVELS))
    ].dropna(subset=["weight", "classification_code", "item_name"])
    if latest.empty:
        return []

    # Map normalized name -> the heaviest row carrying it (dedupe a name that repeats
    # across levels), then match all names at once with a single word-bounded regex.
    by_name: dict[str, pd.Series] = {}
    for _, r in latest.sort_values("weight", ascending=False).iterrows():
        name = _normalize(r["item_name"])
        if name and name not in by_name:
            by_name[name] = r
    if not by_name:
        return []
    names = sorted(by_name, key=len, reverse=True)
    pattern = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")\b")
    matched = list(dict.fromkeys(pattern.findall(q)))
    if not matched:
        return []
    rows = sorted((by_name[n] for n in matched), key=lambda r: r["weight"], reverse=True)
    return rows[:max_items]


def get_item_weights(question: str, ipca_items: pd.DataFrame, max_items: int = 6) -> list[Evidence]:
    """Basket weights of the IPCA items NAMED in the question — Q&A ONLY.

    Kept OUT of build_evidence_table (the brief path): a weight is only worth a
    citation when the user asked about a specific item, so the model can answer
    "arroz pesa 0,50%, passagem aérea 0,67%" with grounded numbers instead of
    refusing for lack of data. No items / no match -> [] (zero regression). Never raises.
    """
    try:
        rows = _match_named_items(question, ipca_items, max_items)
        if not rows:
            return []
        month = pd.to_datetime(rows[0]["_date"]).strftime("%Y-%m")
        return [
            Evidence(
                f"ev_weight_{r['classification_code']}",
                f"Peso na cesta: {r['item_name']}",
                _num(r["weight"]),
                "%",
                month,
                SOURCE_SIDRA,
                "peso (fatia do orçamento das famílias) do item na cesta do IPCA, "
                "mês de referência",
            )
            for r in rows
        ]
    except Exception:  # noqa: BLE001 - Q&A-only helper must never break the answer path
        return []


def get_item_changes(question: str, ipca_items: pd.DataFrame, max_items: int = 4) -> list[Evidence]:
    """Price changes of the IPCA items NAMED in the question — Q&A ONLY.

    Answers the most common question ("quanto subiu o café?") with grounded numbers:
    for each named item, the month variation (m/m), the 12-month variation, and the
    contribution to the headline (p.p.). Q&A-only (never in build_evidence_table). No
    item / no match -> [] (the model still answers qualitatively). Never raises; a
    missing metric column degrades that field to None.
    """
    try:
        rows = _match_named_items(question, ipca_items, max_items)
        if not rows:
            return []
        month = pd.to_datetime(rows[0]["_date"]).strftime("%Y-%m")
        out: list[Evidence] = []
        for r in rows:
            code, name = r["classification_code"], r["item_name"]
            out.append(
                Evidence(
                    f"ev_item_mom_{code}",
                    f"Variação no mês: {name}",
                    _num(r.get("mom")),
                    "%",
                    month,
                    SOURCE_SIDRA,
                    "variação de preço do item no mês (m/m)",
                )
            )
            out.append(
                Evidence(
                    f"ev_item_12m_{code}",
                    f"Variação em 12 meses: {name}",
                    _num(r.get("yoy")),
                    "%",
                    month,
                    SOURCE_SIDRA,
                    "variação acumulada do item em 12 meses",
                )
            )
            out.append(
                Evidence(
                    f"ev_item_contrib_{code}",
                    f"Contribuição no mês: {name}",
                    _num(r.get("contribution_mom")),
                    "p.p.",
                    month,
                    SOURCE_SIDRA,
                    "contribuição do item para o IPCA do mês (peso × variação ÷ 100)",
                )
            )
        return out
    except Exception:  # noqa: BLE001 - Q&A-only helper must never break the answer path
        return []


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
