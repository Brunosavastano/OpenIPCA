from __future__ import annotations

import pandas as pd


def latest_row(df: pd.DataFrame, series_short_name: str) -> pd.Series | None:
    subset = df[df["series_short_name"] == series_short_name].sort_values("date")
    if subset.empty:
        return None
    return subset.iloc[-1]


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
        core_mom = core_3m = float("nan")
        core_assessment = "sem leitura de núcleos suficiente"
    else:
        row = core_mean.iloc[0]
        core_mom = float(row["mom"])
        core_3m = float(row["three_month_saar"])
        core_12m = float(row["rolling_12m"])
        if pd.notna(core_3m) and pd.notna(core_12m) and core_3m > core_12m:
            core_assessment = "núcleos acelerando na margem"
        elif pd.notna(core_3m) and pd.notna(core_12m):
            core_assessment = "núcleos desacelerando na margem"
        else:
            core_assessment = "núcleos ainda sem janela completa"

    alert_count = 0 if alerts.empty else len(alerts)
    alert_phrase = (
        "sem alertas ativos"
        if alert_count == 0
        else f"com {alert_count} alerta(s) ativo(s), incluindo {alerts.iloc[0]['alert_id']}"
    )
    composition = "moderada"
    if alert_count > 0:
        composition = "adversa"
    elif pd.notna(diffusion_mm3) and diffusion_mm3 < 50:
        composition = "mais benigna"

    reference_month = latest_date.strftime("%Y-%m")
    text = (
        f"O IPCA de {reference_month} veio em {ipca_mom:.2f}%, acumulando "
        f"{ipca_12m:.2f}% em 12 meses. A composição foi {composition}, "
        f"com destaque altista para {top_positive} e {negative_label} de {top_negative}. "
        f"A média dos núcleos avançou {core_mom:.2f}% no mês e roda a {core_3m:.2f}% "
        f"em 3m anualizado, sinalizando {core_assessment}. A difusão ficou em "
        f"{diffusion_value:.1f}% ({diffusion_mm3:.1f}% em MM3M), {alert_phrase}."
    )
    return {"reference_month": reference_month, "diagnostic": text}
