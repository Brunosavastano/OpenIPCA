from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ipca_dashboard.charts import (  # noqa: E402
    contribution_ranking,
    core_fan,
    core_lines,
    diffusion_line,
    heatmap_groups,
    ipca_diffusion_scatter,
    stacked_contribution,
    waterfall_latest,
)
from ipca_dashboard.config import OUTPUTS_DIR, PROCESSED_DIR, load_yaml  # noqa: E402


st.set_page_config(page_title="IPCA Macro Dashboard", layout="wide")


CSS = """
<style>
  .main .block-container { padding-top: 1.5rem; max-width: 1400px; }
  h1, h2, h3 { color: #111827; letter-spacing: 0; }
  [data-testid="stMetric"] {
    background: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 14px 16px;
  }
  [data-testid="stMetricLabel"] { color: #6B7280; }
  [data-testid="stMetricValue"] { color: #111827; font-size: 1.55rem; }
  .diagnostic {
    border-left: 4px solid #111827;
    background: #F9FAFB;
    padding: 16px 18px;
    border-radius: 6px;
    font-size: 1.02rem;
    line-height: 1.55;
  }
  .small-note { color: #6B7280; font-size: 0.9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_data() -> dict[str, pd.DataFrame]:
    paths = {
        "bcb": PROCESSED_DIR / "bcb_series_monthly.parquet",
        "items": PROCESSED_DIR / "ipca_items_monthly.parquet",
        "cores": PROCESSED_DIR / "core_metrics_monthly.parquet",
        "alerts": PROCESSED_DIR / "alerts.parquet",
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("\n".join(missing))
    return {name: pd.read_parquet(path) for name, path in paths.items()}


def load_diagnostic() -> str:
    path = OUTPUTS_DIR / "diagnostic_latest.json"
    if not path.exists():
        return "Diagnóstico ainda não gerado."
    return json.loads(path.read_text(encoding="utf-8")).get("diagnostic", "Diagnóstico indisponível.")


def fmt(value: float | int | None, suffix: str = "%") -> str:
    if value is None or pd.isna(value):
        return "n.d."
    return f"{value:.2f}{suffix}"


def latest_series_row(bcb: pd.DataFrame, name: str) -> pd.Series | None:
    subset = bcb[bcb["series_short_name"] == name].sort_values("date")
    if subset.empty:
        return None
    return subset.iloc[-1]


def page_executive(data: dict[str, pd.DataFrame]) -> None:
    bcb, items, cores, alerts = data["bcb"], data["items"], data["cores"], data["alerts"]
    latest_date = pd.to_datetime(bcb["date"]).max()
    ipca = latest_series_row(bcb, "IPCA")
    diffusion = latest_series_row(bcb, "Difusao")
    core_mean = cores[
        (cores["core_set_name"] == "bcb_compact")
        & (cores["core_name"].isin(["Media", "Média"]))
        & (cores["date"] == latest_date)
    ]
    core_row = core_mean.iloc[0] if not core_mean.empty else None

    st.title("IPCA Macro Dashboard")
    st.caption(f"Último dado processado: {latest_date:%Y-%m} | Fontes: BCB/SGS e IBGE/SIDRA")
    cols = st.columns(6)
    cols[0].metric("IPCA m/m", fmt(ipca["mom"] if ipca is not None else None))
    cols[1].metric("IPCA 12m", fmt(ipca["rolling_12m"] if ipca is not None else None))
    cols[2].metric("IPCA 3m saar", fmt(ipca["three_month_saar"] if ipca is not None else None))
    cols[3].metric("Média núcleos 3m", fmt(core_row["three_month_saar"] if core_row is not None else None))
    cols[4].metric("Difusão MM3M", fmt(diffusion["moving_average_3m"] if diffusion is not None else None))
    cols[5].metric("Alertas ativos", len(alerts), "")

    st.markdown(f"<div class='diagnostic'>{load_diagnostic()}</div>", unsafe_allow_html=True)

    left, right = st.columns([1.25, 1])
    with left:
        st.plotly_chart(stacked_contribution(items), use_container_width=True)
    with right:
        st.plotly_chart(diffusion_line(bcb), use_container_width=True)
    st.plotly_chart(core_lines(cores, "bcb_compact", "three_month_saar"), use_container_width=True)

    if not alerts.empty:
        st.subheader("Alertas ativos")
        st.dataframe(alerts[["reference_month", "severity", "metric", "value", "message"]], use_container_width=True)


def page_decomposition(data: dict[str, pd.DataFrame]) -> None:
    items = data["items"]
    st.header("Decomposição do IPCA")
    dates = sorted(pd.to_datetime(items["date"]).dropna().unique())
    selected_date = st.selectbox("Mês de referência", dates, index=len(dates) - 1, format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m"))
    selected_date = pd.Timestamp(selected_date)
    level = st.selectbox("Nível para ranking", ["group", "subgroup", "item", "subitem"], index=3)

    st.plotly_chart(stacked_contribution(items), use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(waterfall_latest(items, selected_date), use_container_width=True)
    with right:
        st.plotly_chart(contribution_ranking(items, selected_date, level), use_container_width=True)
    st.plotly_chart(heatmap_groups(items), use_container_width=True)

    latest = items[(items["date"] == selected_date) & (items["level"] == level)].copy()
    st.download_button(
        "Baixar ranking CSV",
        latest.sort_values("contribution_mom", ascending=False).to_csv(index=False).encode("utf-8"),
        file_name=f"ranking_{level}_{selected_date:%Y_%m}.csv",
        mime="text/csv",
    )


def page_cores(data: dict[str, pd.DataFrame]) -> None:
    cores = data["cores"]
    core_sets = load_yaml("core_sets.yaml").get("core_sets", {})
    labels = {key: value.get("label", key) for key, value in core_sets.items()}
    selected = st.selectbox("Preset de núcleos", list(labels), format_func=lambda key: labels[key])
    metric = st.selectbox("Métrica", ["rolling_12m", "three_month_saar", "mom", "moving_average_3m"], index=1)
    st.header("Monitor de núcleos")
    st.plotly_chart(core_lines(cores, selected, metric), use_container_width=True)
    st.plotly_chart(core_fan(cores, selected, metric), use_container_width=True)
    latest = cores[cores["core_set_name"] == selected].sort_values("date").groupby("core_name").tail(1)
    st.dataframe(latest.sort_values("three_month_saar", ascending=False), use_container_width=True)


def page_diffusion(data: dict[str, pd.DataFrame]) -> None:
    bcb, items = data["bcb"], data["items"]
    st.header("Monitor de difusão")
    st.plotly_chart(diffusion_line(bcb), use_container_width=True)
    st.plotly_chart(ipca_diffusion_scatter(bcb), use_container_width=True)

    subitems = items[items["level"] == "subitem"].copy()
    subitems["positive"] = subitems["mom"] > 0
    diffusion_by_group = (
        subitems.groupby(["date", "group_classification_code"])["positive"].mean().mul(100).reset_index()
    )
    latest = diffusion_by_group[diffusion_by_group["date"] == diffusion_by_group["date"].max()]
    st.subheader("Difusão calculada por grupo - último mês")
    st.dataframe(latest.rename(columns={"positive": "diffusion_pct"}), use_container_width=True)


def page_alerts(data: dict[str, pd.DataFrame]) -> None:
    alerts = data["alerts"]
    st.header("Alertas")
    if alerts.empty:
        st.info("Nenhum alerta ativo no último processamento.")
    else:
        st.dataframe(alerts, use_container_width=True)
        st.download_button(
            "Baixar alertas CSV",
            alerts.to_csv(index=False).encode("utf-8"),
            file_name="alerts.csv",
            mime="text/csv",
        )


def page_methodology(data: dict[str, pd.DataFrame]) -> None:
    st.header("Metodologia")
    st.markdown(
        """
        **Fontes.** BCB/SGS para IPCA headline, agregados macro, núcleos e difusão; IBGE/SIDRA
        tabela 7060 para pesos, variações e hierarquia de grupos, subgrupos, itens e subitens.

        **Contribuição mensal.** `peso_mensal * variacao_mensal / 100`, em pontos percentuais.

        **3m saar.** Produto dos fatores dos três últimos meses elevado à quarta potência, menos um.

        **Núcleos.** A média dos núcleos é calculada a partir do preset selecionado em `config/core_sets.yaml`.

        **Alertas.** Regras declarativas em `config/alert_rules.yaml`; o dashboard exibe apenas os
        alertas disparados no último processamento.

        **Validação.** O pipeline checa duplicidades, faixas plausíveis, disponibilidade do preset
        default e diferença entre soma das contribuições por grupo e headline.
        """
    )
    validation_path = OUTPUTS_DIR / "validation_report.csv"
    if validation_path.exists():
        st.subheader("Relatório de validação")
        validation = pd.read_csv(validation_path)
        st.dataframe(validation, use_container_width=True)
    st.subheader("Downloads")
    for name, frame in data.items():
        st.download_button(
            f"Baixar {name}.csv",
            frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{name}.csv",
            mime="text/csv",
        )


def main() -> None:
    try:
        data = load_data()
    except FileNotFoundError as exc:
        st.title("IPCA Macro Dashboard")
        st.error("Dados processados não encontrados.")
        st.code("python -m ipca_dashboard.pipeline run --start 2020-01\nstreamlit run dashboard/app.py")
        st.caption(str(exc))
        return

    page = st.sidebar.radio(
        "Navegação",
        ["Painel executivo", "Decomposição", "Núcleos", "Difusão", "Alertas", "Metodologia"],
    )
    if page == "Painel executivo":
        page_executive(data)
    elif page == "Decomposição":
        page_decomposition(data)
    elif page == "Núcleos":
        page_cores(data)
    elif page == "Difusão":
        page_diffusion(data)
    elif page == "Alertas":
        page_alerts(data)
    else:
        page_methodology(data)


if __name__ == "__main__":
    main()
