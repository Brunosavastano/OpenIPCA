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
from ipca_dashboard.ai.env import load_env_once  # noqa: E402
from ipca_dashboard.config import OUTPUTS_DIR, PROCESSED_DIR, load_yaml  # noqa: E402
from ipca_dashboard.diagnostics import classify_latest_regime  # noqa: E402
from ipca_dashboard.glossary import (  # noqa: E402
    CONCEPTS,
    CORE_TERMS,
    SEVERITY_PT,
    describe,
)
from ipca_dashboard.transforms import calculate_diffusion_from_items  # noqa: E402

load_env_once()  # honor a local .env for BYOK; no-op without python-dotenv


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
    color: #111827;
    padding: 16px 18px;
    border-radius: 6px;
    font-size: 1.02rem;
    line-height: 1.55;
  }
  .diagnostic strong { color: #111827; }
  .small-note { color: #6B7280; font-size: 0.9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


PROCESSED_PATHS = {
    "bcb": PROCESSED_DIR / "bcb_series_monthly.parquet",
    "items": PROCESSED_DIR / "ipca_items_monthly.parquet",
    "cores": PROCESSED_DIR / "core_metrics_monthly.parquet",
    "alerts": PROCESSED_DIR / "alerts.parquet",
}


def processed_signature() -> tuple:
    """File signature (path + mtime) so the cache invalidates after a rebuild."""
    return tuple(
        (name, str(path), path.stat().st_mtime_ns)
        for name, path in PROCESSED_PATHS.items()
        if path.exists()
    )


@st.cache_data(show_spinner=False)
def load_data(signature: tuple) -> dict[str, pd.DataFrame]:
    missing = [str(path) for path in PROCESSED_PATHS.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("\n".join(missing))
    return {name: pd.read_parquet(path) for name, path in PROCESSED_PATHS.items()}


def load_diagnostic() -> str:
    path = OUTPUTS_DIR / "diagnostic_latest.json"
    if not path.exists():
        return "Diagnóstico ainda não gerado."
    return json.loads(path.read_text(encoding="utf-8")).get("diagnostic", "Diagnóstico indisponível.")


REPORTS_LATEST = ROOT / "reports" / "latest"


def render_ai_replay() -> None:
    """Show the pre-generated, auditable AI brief + orchestration trace.

    "AI Replay Mode": the public demo replays an artifact generated offline
    (BYOK). If no artifact exists yet, the deterministic brief above is the
    floor and this stays quiet.
    """
    brief_path = REPORTS_LATEST / "ai_brief.md"
    trace_path = REPORTS_LATEST / "ai_trace.json"
    if not brief_path.exists():
        return
    with st.expander("🤖 AI Replay Mode — como a IA montou este brief", expanded=False):
        st.caption(
            "Brief pré-gerado e auditável. Sem chamada de IA ao vivo na demo; "
            "toda afirmação é rastreável a uma evidência. Rode localmente com sua "
            "própria chave para gerar novas leituras."
        )
        st.markdown(brief_path.read_text(encoding="utf-8"))
        if trace_path.exists():
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            with st.expander("🔎 Ver os bastidores (como a IA chegou a isto)", expanded=False):
                st.caption(
                    "Passo a passo do que a IA consultou (somente dados oficiais já "
                    "calculados) antes de escrever — para quem quiser auditar a leitura."
                )
                st.json(trace)


def _alert_messages() -> dict[str, str]:
    """Map alert_id -> human-readable message from config (reused, not hard-coded)."""
    try:
        rules = load_yaml("alert_rules.yaml").get("rules", [])
    except Exception:  # noqa: BLE001 - missing/invalid config must not break the page
        return {}
    return {r["id"]: r.get("message", r["id"]) for r in rules if "id" in r}


def render_active_alerts(alerts: pd.DataFrame) -> None:
    """Active alerts in plain language: the config message + translated severity."""
    st.subheader("Alertas ativos")
    st.caption(describe("alertas"))
    if alerts.empty:
        st.info("Nenhum alerta ativo neste mês.")
        return
    messages = _alert_messages()
    badge = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪"}
    for _, row in alerts.iterrows():
        alert_id = str(row.get("alert_id", ""))
        sev = str(row.get("severity", "info"))
        text = messages.get(alert_id, alert_id)
        sev_pt = SEVERITY_PT.get(sev, sev)
        st.markdown(f"{badge.get(sev, '⚪')} **[{sev_pt}]** {text}")


def render_glossary() -> None:
    """A persistent, plain-language glossary for readers without macro context."""
    with st.expander("📖 O que significam estes termos?", expanded=False):
        for text in CONCEPTS.values():
            st.markdown(f"- {text}")
        st.markdown("**Núcleos do IPCA:**")
        for text in CORE_TERMS.values():
            st.markdown(f"- {text}")


def freshness_notice() -> tuple[str, str] | None:
    """Return (severity, details) for the freshness check, if not 'pass'."""
    path = OUTPUTS_DIR / "validation_report.csv"
    if not path.exists():
        return None
    report = pd.read_csv(path)
    row = report[report["check"] == "critical_series_freshness"]
    if row.empty:
        return None
    status = str(row.iloc[0]["status"])
    if status == "pass":
        return None
    return status, str(row.iloc[0]["details"])


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

    notice = freshness_notice()
    if notice is not None:
        severity, details = notice
        (st.error if severity == "block" else st.warning)(f"Freshness: {details}")

    # Each card carries a plain-language tooltip ("(i)") via st.metric(help=...).
    cols = st.columns(6)
    cols[0].metric("IPCA m/m", fmt(ipca["mom"] if ipca is not None else None), help=describe("IPCA m/m"))
    cols[1].metric("IPCA 12m", fmt(ipca["rolling_12m"] if ipca is not None else None), help=describe("IPCA 12m"))
    cols[2].metric("IPCA MM3M", fmt(ipca["moving_average_3m"] if ipca is not None else None), help=describe("IPCA MM3M"))
    cols[3].metric("Média núcleos MM3M", fmt(core_row["moving_average_3m"] if core_row is not None else None), help=describe("Média núcleos MM3M"))
    cols[4].metric("Difusão MM3M", fmt(diffusion["moving_average_3m"] if diffusion is not None else None), help=describe("Difusão MM3M"))
    cols[5].metric("Alertas ativos", len(alerts), help=describe("Alertas ativos"))

    regime = classify_latest_regime(bcb)
    st.markdown(f"**Regime inflacionário:** {regime.label_pt}")
    regime_explanation = describe(regime.label_pt)
    if regime_explanation:
        st.caption(regime_explanation)
    st.caption(
        "Momentum em MM3M (média móvel de 3 meses, sem ajuste sazonal/NSA). "
        "A versão anualizada com ajuste sazonal (SA) chega no v0.2. "
        "Regime classificado por regra determinística (headline × difusão)."
    )

    st.markdown(f"<div class='diagnostic'>{load_diagnostic()}</div>", unsafe_allow_html=True)

    render_ai_replay()
    render_glossary()

    left, right = st.columns([1.25, 1])
    with left:
        st.plotly_chart(stacked_contribution(items), use_container_width=True)
    with right:
        st.plotly_chart(diffusion_line(bcb), use_container_width=True)
    st.plotly_chart(core_lines(cores, "bcb_compact", "moving_average_3m"), use_container_width=True)

    render_active_alerts(alerts)


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

    # Completeness warning (only if the column exists in the processed data).
    complete_col = "is_complete" if "is_complete" in cores.columns else "is_complete_core_set"
    if complete_col in cores.columns:
        mean_rows = cores[
            (cores["core_set_name"] == selected) & (cores["core_name"].isin(["Media", "Média"]))
        ].sort_values("date")
        if not mean_rows.empty:
            latest_mean = mean_rows.iloc[-1]
            if not bool(latest_mean.get(complete_col, True)):
                avail = int(latest_mean.get("n_members_available", 0))
                exp = int(latest_mean.get("n_members_expected", 0))
                missing = latest_mean.get("missing_members", "")
                st.warning(
                    f"Preset incompleto no mês mais recente: {avail}/{exp} séries disponíveis. "
                    f"Faltando: {missing}. A média é omitida quando o preset está incompleto."
                )

    metric_labels = {
        "moving_average_3m": "MM3M (m/m, NSA)",
        "rolling_12m": "12m",
        "mom": "m/m",
        "three_month_saar": "3m anualizado (NSA, experimental)",
    }
    metric = st.selectbox(
        "Métrica", list(metric_labels), index=0, format_func=lambda key: metric_labels[key]
    )
    st.header("Monitor de núcleos")
    st.caption("Momentum sem ajuste sazonal (NSA). Versão com ajuste sazonal (SA) chega no v0.2.")
    st.plotly_chart(core_lines(cores, selected, metric), use_container_width=True)
    st.plotly_chart(core_fan(cores, selected, metric), use_container_width=True)
    latest = cores[cores["core_set_name"] == selected].sort_values("date").groupby("core_name").tail(1)
    st.dataframe(latest.sort_values("moving_average_3m", ascending=False), use_container_width=True)


def page_diffusion(data: dict[str, pd.DataFrame]) -> None:
    bcb, items = data["bcb"], data["items"]
    st.header("Monitor de difusão")
    st.plotly_chart(diffusion_line(bcb), use_container_width=True)
    st.plotly_chart(ipca_diffusion_scatter(bcb), use_container_width=True)

    diffusion_by_group = calculate_diffusion_from_items(
        items, level="subitem", group_col="group_classification_code"
    )
    latest = diffusion_by_group[diffusion_by_group["date"] == diffusion_by_group["date"].max()]
    st.subheader("Difusão calculada por grupo - último mês")
    st.dataframe(latest.rename(columns={"diffusion": "diffusion_pct"}), use_container_width=True)


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

        **Momentum de curto prazo.** A interface usa MM3M (média móvel de 3 meses da
        variação m/m) porque as séries mensais são brutas, sem ajuste sazonal (NSA).
        A coluna `three_month_saar` segue disponível para auditoria/exploração, mas deve
        ser lida como 3m anualizado NSA experimental, não como SAAR.

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
        data = load_data(processed_signature())
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
