from __future__ import annotations

import pandas as pd

from ipca_dashboard.regime import RegimeResult, classify_inflation_regime


def latest_row(
    df: pd.DataFrame,
    series_short_name: str,
    reference_date: pd.Timestamp | None = None,
) -> pd.Series | None:
    subset = df[df["series_short_name"] == series_short_name].sort_values("date")
    if reference_date is not None:
        subset = subset[pd.to_datetime(subset["date"]) == reference_date]
    if subset.empty:
        return None
    return subset.iloc[-1]


def build_regime_context(bcb: pd.DataFrame) -> dict:
    """Assemble the deterministic signals the regime classifier needs.

    Reuses existing pipeline columns (no recompute): the headline IPCA m/m
    expanding percentile and the diffusion MM3M percentile.
    """
    if bcb.empty:
        return {}
    latest_date = pd.to_datetime(bcb["date"]).max()
    ipca = latest_row(bcb, "IPCA", latest_date)
    diffusion = latest_row(bcb, "Difusao", latest_date)
    context: dict[str, object] = {}
    if ipca is not None and "percentile_since_2012" in ipca:
        context["headline_percentile"] = (
            float(ipca["percentile_since_2012"])
            if pd.notna(ipca["percentile_since_2012"])
            else None
        )
    if diffusion is not None and "moving_average_3m_percentile" in diffusion:
        context["diffusion_mm3_percentile"] = (
            float(diffusion["moving_average_3m_percentile"])
            if pd.notna(diffusion["moving_average_3m_percentile"])
            else None
        )
    return context


def classify_latest_regime(bcb: pd.DataFrame) -> RegimeResult:
    """Classify the inflation regime for the latest month from `bcb`."""
    return classify_inflation_regime(build_regime_context(bcb))


def build_diagnostic_text(
    bcb: pd.DataFrame,
    ipca_items: pd.DataFrame,
    core_metrics: pd.DataFrame,
    alerts: pd.DataFrame,
    core_set_name: str = "bcb_compact",
) -> dict[str, str]:
    if bcb.empty:
        return {"reference_month": "", "diagnostic": "Sem dados processados."}

    latest_date = pd.to_datetime(bcb["date"]).max()
    ipca = latest_row(bcb, "IPCA")
    diffusion = latest_row(bcb, "Difusao")
    core_mean = core_metrics[
        (core_metrics["core_set_name"] == core_set_name)
        & (core_metrics["core_name"].isin(["Media", "Média"]))
        & (core_metrics["date"] == latest_date)
    ]

    latest_groups = ipca_items[
        (ipca_items["date"] == latest_date) & (ipca_items["level"] == "group")
    ].copy()
    top_positive = "sem destaque"
    top_negative = "sem destaque"
    negative_label = "contribuição baixista"
    if not latest_groups.empty:
        pos = latest_groups.sort_values("contribution_mom", ascending=False).iloc[0]
        neg = latest_groups.sort_values("contribution_mom", ascending=True).iloc[0]
        top_positive = f"{pos['item_name']} ({pos['contribution_mom']:.2f} p.p.)"
        top_negative = f"{neg['item_name']} ({neg['contribution_mom']:.2f} p.p.)"
        if neg["contribution_mom"] >= 0:
            negative_label = "menor contribuição"

    ipca_mom = float(ipca["mom"]) if ipca is not None and pd.notna(ipca["mom"]) else float("nan")
    ipca_12m = (
        float(ipca["rolling_12m"])
        if ipca is not None and pd.notna(ipca["rolling_12m"])
        else float("nan")
    )
    diffusion_value = (
        float(diffusion["mom"])
        if diffusion is not None and pd.notna(diffusion["mom"])
        else float("nan")
    )
    diffusion_mm3 = (
        float(diffusion["moving_average_3m"])
        if diffusion is not None and pd.notna(diffusion["moving_average_3m"])
        else float("nan")
    )

    if core_mean.empty:
        core_mom = core_mm3 = float("nan")
        core_assessment = "sem leitura de núcleos suficiente"
    else:
        row = core_mean.iloc[0]
        core_mom = float(row["mom"])
        core_mm3 = float(row["moving_average_3m"])
        if pd.notna(core_mm3):
            core_assessment = "leitura de curto prazo em MM3M (NSA)"
        else:
            core_assessment = "núcleos ainda sem janela completa"

    alert_count = 0 if alerts.empty else len(alerts)
    if alert_count == 0:
        alert_phrase = "sem alertas ativos"
    else:
        # Prefer the human-readable message over the raw alert_id; the message may
        # carry technical wording but never the bare machine id.
        first = alerts.iloc[0]
        first_alert = (
            first["message"]
            if "message" in alerts.columns and pd.notna(first.get("message"))
            else "alerta ativo sem descrição configurada"
        )
        alert_phrase = f"com {alert_count} alerta(s) ativo(s), incluindo: {first_alert}"
    composition = "moderada"
    if alert_count > 0:
        composition = "adversa"
    elif pd.notna(diffusion_mm3) and diffusion_mm3 < 50:
        composition = "mais benigna"

    regime = classify_inflation_regime(build_regime_context(bcb))

    reference_month = latest_date.strftime("%Y-%m")
    text = (
        f"O IPCA de {reference_month} veio em {ipca_mom:.2f}%, acumulando "
        f"{ipca_12m:.2f}% em 12 meses. A composição foi {composition}, "
        f"com destaque altista para {top_positive} e {negative_label} de {top_negative}. "
        f"A média dos núcleos avançou {core_mom:.2f}% no mês e roda a {core_mm3:.2f}% "
        f"em MM3M (NSA), sinalizando {core_assessment}. A difusão ficou em "
        f"{diffusion_value:.1f}% ({diffusion_mm3:.1f}% em MM3M), {alert_phrase}. "
        f"Regime: {regime.label_pt}."
    )
    return {
        "reference_month": reference_month,
        "diagnostic": text,
        "regime": regime.regime,
        "regime_label": regime.label_pt,
        "regime_rule_id": regime.rule_id,
    }
