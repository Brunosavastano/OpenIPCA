from __future__ import annotations

import json
import sys
from html import escape
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
from ipca_dashboard.ai.env import bridge_secrets_to_env, load_env_once  # noqa: E402
from ipca_dashboard.ai.evidence import resolve_claim_evidence  # noqa: E402
from ipca_dashboard.ai.qa_replay import CURATED_QUESTIONS, answer_with_replay  # noqa: E402
from ipca_dashboard.ai.staleness import is_stale, reference_month_from_brief  # noqa: E402
from ipca_dashboard.ai.trace import (  # noqa: E402
    brief_stamp_line,
    load_brief_metadata,
    load_trace_summary,
)
from ipca_dashboard.config import OUTPUTS_DIR, PROCESSED_DIR, load_yaml  # noqa: E402
from ipca_dashboard.diagnostics import classify_latest_regime  # noqa: E402
from ipca_dashboard.glossary import (  # noqa: E402
    CONCEPTS,
    CORE_TERMS,
    METRIC_LABELS,
    SEVERITY_PT,
    describe,
)
from ipca_dashboard.hierarchy import (  # noqa: E402
    LEVEL_LABEL_PT,
    children,
    node_label,
    top_level_rows,
)
from ipca_dashboard.transforms import calculate_diffusion_from_items, top_movers  # noqa: E402
from ipca_dashboard.validation import summarize_report  # noqa: E402

# On a deploy (e.g. Streamlit Community Cloud) the AI key is set as a *secret*.
# The AI config reads os.environ, so mirror secrets into it (real env vars win).
# Accessing st.secrets with no secrets.toml raises, so guard the read.
try:
    _deploy_secrets = st.secrets
except Exception:
    _deploy_secrets = None
bridge_secrets_to_env(_deploy_secrets)
# Honor a local .env for BYOK; override=False means real env/secrets above win.
load_env_once()


st.set_page_config(
    page_title="OpenIPCA — IPCA além da headline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


CSS = """
<style>
  /* Institutional "terminal" theme (Bloomberg/Aladdin direction). IBM Plex Sans
     for UI, IBM Plex Mono (tabular) for numbers. Coherent with config.toml. */
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  html, body, [class*="css"], .stApp { font-family: 'IBM Plex Sans', sans-serif; }
  .main .block-container { padding-top: 1.4rem; max-width: 1400px; }
  h1 { font-size: 1.55rem; font-weight: 600; letter-spacing: -.005em; color: #E6EAF1; }
  h2, h3 { font-weight: 600; color: #E6EAF1; letter-spacing: 0; }
  [data-testid="stCaptionContainer"], .small-note { color: #8A93A3; }

  /* sidebar */
  [data-testid="stSidebar"] { background: #11161F; border-right: 1px solid #222A36; }

  /* KPI tiles — custom grid (st.markdown HTML). Equal height via the grid; each
     tile = label + (?) tooltip, mono value, plain colored delta, muted note. */
  .kpi-grid {
    display: grid; grid-template-columns: repeat(6, 1fr);
    grid-auto-rows: 1fr; gap: 10px; margin: 2px 0 6px;
  }
  @media (max-width: 1100px) { .kpi-grid { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 640px)  { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
  .kpi {
    display: flex; flex-direction: column;
    background: #11161F; border: 1px solid #222A36; border-radius: 6px;
    padding: 13px 14px; min-width: 0;
  }
  .kpi-head { display: flex; align-items: center; gap: 5px; margin-bottom: 6px; }
  .kpi-label {
    color: #8A93A3; font-family: 'IBM Plex Mono', monospace; font-size: .66rem;
    font-weight: 500; letter-spacing: .1em; text-transform: uppercase;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0;
  }
  .kpi-info {
    flex: none; cursor: help; color: #5A6373; font-size: .6rem; font-weight: 600; line-height: 1;
    border: 1px solid #2E3845; border-radius: 50%;
    width: 14px; height: 14px; display: inline-flex; align-items: center; justify-content: center;
  }
  .kpi-info:hover { color: #8A93A3; border-color: #3A4656; }
  .kpi-value {
    color: #E6EAF1; font-family: 'IBM Plex Mono', monospace;
    font-variant-numeric: tabular-nums; font-size: 1.7rem; font-weight: 500; line-height: 1.15;
  }
  .kpi-delta {
    font-family: 'IBM Plex Mono', monospace; font-size: .8rem; font-weight: 500;
    margin-top: 4px; min-height: 1.05rem;
  }
  .kpi-delta.up   { color: #E5484D; }   /* inverse: rising inflation = bad = red */
  .kpi-delta.down { color: #35B07D; }   /* falling = good = green */
  .kpi-delta.flat { color: #8A93A3; }
  .kpi-note { color: #5A6373; font-size: .64rem; margin-top: 3px; }

  /* "Vilões e aliados" — the month's biggest 12m movers, in everyday names */
  .movers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 2px 0 6px; }
  @media (max-width: 640px) { .movers-grid { grid-template-columns: 1fr; } }
  .movers-col {
    background: #11161F; border: 1px solid #222A36; border-radius: 6px; padding: 12px 14px;
  }
  .movers-title-up { color: #E5484D; }
  .movers-title-down { color: #35B07D; }
  .mover-row { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; }
  .mover-name {
    color: #E6EAF1; font-size: .86rem;
    min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .mover-val {
    font-family: 'IBM Plex Mono', monospace; font-size: .86rem; font-weight: 500; flex: none;
  }
  .mover-val.up { color: #E5484D; }
  .mover-val.down { color: #35B07D; }

  /* buttons & input */
  .stButton > button[kind="primary"] {
    background: #E8943A; color: #0A0E14; font-weight: 600; border: 0; border-radius: 5px;
  }
  .stButton > button[kind="primary"]:hover { background: #F4A94E; color: #0A0E14; }
  /* secondary = "card" buttons (suggested questions, CTA): dark box + amber arrow */
  .stButton > button[kind="secondary"] {
    background: #11161F; color: #E6EAF1; border: 1px solid #222A36; border-radius: 6px;
    font-weight: 400; text-align: left; justify-content: flex-start; gap: 9px;
  }
  .stButton > button[kind="secondary"]:hover {
    background: #161D28; border-color: #2E3845; color: #E6EAF1;
  }
  .stButton > button[kind="secondary"]::before { content: "\\203A"; color: #E8943A; font-weight: 700; }
  [data-testid="stTextInput"] input {
    background: #161D28; border: 1px solid #2E3845; color: #E6EAF1; border-radius: 5px;
  }
  /* selectboxes ("Conjunto de núcleos", "Métrica"…) framed like the cards */
  [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background: #11161F; border-color: #222A36 !important; border-radius: 8px;
  }

  /* callout boxes */
  .diagnostic {
    background: #11161F; border: 1px solid #222A36;
    border-left: 3px solid #4A8FE0;          /* reading = info blue */
    color: #E6EAF1; padding: 15px 18px; border-radius: 6px; line-height: 1.55;
    margin-bottom: 16px;                     /* breathing room before the CTA box */
  }
  .diagnostic strong { color: #FFFFFF; }
  .ask-cta { display: none; }
  /* "Pergunte ao IPCA" CTA: a bordered container (so the button sits inside the box),
     scoped by its .ask-cta marker to the innermost wrapper (not the page/sidebar). */
  [data-testid="stVerticalBlockBorderWrapper"]:has(.ask-cta):not(:has([data-testid="stVerticalBlockBorderWrapper"] .ask-cta)) {
    background: linear-gradient(90deg, rgba(53,176,125,.10), rgba(0,0,0,0) 70%), #11161F;
    border: 1px solid #2E3845 !important; border-left: 3px solid #35B07D !important;
    border-radius: 8px;
  }
  .callout-title {
    font-family: 'IBM Plex Mono', monospace; font-size: .62rem; font-weight: 600;
    letter-spacing: .14em; text-transform: uppercase; margin: 0 0 7px;
  }
  .callout-title.info { color: #4A8FE0; }
  .callout-title.cta  { color: #35B07D; }

  /* alert badges */
  .badge {
    font-family: 'IBM Plex Mono', monospace; font-size: .62rem; letter-spacing: .1em;
    text-transform: uppercase; padding: 3px 8px; border-radius: 3px;
  }
  .badge.crit { color: #E5484D; border: 1px solid rgba(229,72,77,.4); background: rgba(229,72,77,.12); }
  .badge.high { color: #EC7A3D; border: 1px solid rgba(236,122,61,.4); background: rgba(236,122,61,.12); }
  .badge.low  { color: #E0A046; border: 1px solid rgba(224,160,70,.4); background: rgba(224,160,70,.12); }
  .badge.info { color: #4A8FE0; border: 1px solid rgba(74,143,224,.4); background: rgba(74,143,224,.12); }

  /* active alerts as bordered cards with a severity left accent */
  .alert-box {
    display: flex; align-items: center; gap: 10px;
    background: #11161F; border: 1px solid #222A36; border-left: 3px solid #2E3845;
    border-radius: 6px; padding: 10px 13px; margin-bottom: 8px; color: #E6EAF1;
  }
  .alert-box.crit { border-left-color: #E5484D; }
  .alert-box.high { border-left-color: #EC7A3D; }
  .alert-box.low  { border-left-color: #E0A046; }
  .alert-box.info { border-left-color: #4A8FE0; }
  .alert-box .badge { flex: none; }
  .alert-box .alert-text { line-height: 1.4; }

  /* Q&A answer mode seal — sober mono pill instead of an emoji */
  .mode-seal {
    font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .08em;
    text-transform: uppercase; padding: 3px 9px; border-radius: 3px;
    border: 1px solid #2E3845; color: #8A93A3;
  }
  .mode-seal.live { color: #35B07D; border-color: rgba(53,176,125,.45); }
  .mode-seal.refused { color: #E5484D; border-color: rgba(229,72,77,.45); }

  /* sidebar brand + nav (turns st.sidebar.radio into a terminal menu) */
  [data-testid="stSidebar"] .brand { display: flex; align-items: center; gap: 9px; padding: 4px 4px 0; }
  [data-testid="stSidebar"] .brand-mark {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; border-radius: 6px; background: #E8943A; color: #0A0E14;
    font-family: 'IBM Plex Mono', monospace; font-weight: 700; font-size: .95rem;
  }
  [data-testid="stSidebar"] .brand-name { font-weight: 600; font-size: 1.05rem; color: #E6EAF1; letter-spacing: -.01em; }
  [data-testid="stSidebar"] .brand-accent { color: #E8943A; }  /* "IPCA" in the logo amber */
  [data-testid="stSidebar"] .nav-label {
    font-family: 'IBM Plex Mono', monospace; font-size: .6rem; letter-spacing: .18em;
    text-transform: uppercase; color: #5A6373; margin: 18px 4px 6px;
  }
  [data-testid="stSidebar"] [role="radiogroup"] { gap: 1px; }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"] {
    display: flex; align-items: center; gap: 9px; width: 100%; margin: 0; padding: 7px 10px;
    border-left: 3px solid transparent; border-radius: 6px; cursor: pointer;
  }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"]:hover { background: #161D28; }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"] > div:first-child { display: none; }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"]::before {
    content: ""; width: 8px; height: 8px; border-radius: 50%; background: transparent; flex: none;
  }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p {
    color: #B7BECB; font-size: .92rem; margin: 0;
  }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {
    background: #161D28; border-left-color: #E8943A;
  }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"]:has(input:checked)::before { background: #E8943A; width: 9px; height: 9px; box-shadow: 0 0 9px rgba(232,148,58,.9); }
  [data-testid="stSidebar"] [role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) div[data-testid="stMarkdownContainer"] p {
    color: #E8943A; font-weight: 600;
  }

  /* top status strip (terminal-style header band) */
  .status-strip {
    display: flex; align-items: center; justify-content: space-between;
    font-family: 'IBM Plex Mono', monospace; font-size: .64rem; letter-spacing: .12em;
    text-transform: uppercase; color: #8A93A3;
    border-bottom: 1px solid #222A36; padding: 0 2px 9px; margin-bottom: 14px;
  }
  .status-strip .strip-left { display: flex; align-items: center; gap: 8px; }
  .status-strip .dot { width: 7px; height: 7px; border-radius: 50%; background: #E8943A; }
  .status-strip .strip-right { color: #5A6373; }
  /* data-quality seal: MUST be able to degrade (amber/red) — a badge that can
     never turn red is a vanity seal, not a trust signal. */
  .status-strip .seal-ok { color: #35B07D; }
  .status-strip .seal-warn { color: #E0A046; }
  .status-strip .seal-block { color: #E5484D; }

  /* regime pill */
  .regime-row { display: flex; align-items: center; gap: 10px; margin: 4px 0 2px; flex-wrap: wrap; }
  .regime-key { color: #8A93A3; }
  .regime-pill {
    font-family: 'IBM Plex Mono', monospace; font-size: .66rem; letter-spacing: .12em;
    text-transform: uppercase; color: #E8943A;
    border: 1px solid rgba(232,148,58,.5); background: rgba(232,148,58,.08);
    padding: 4px 10px; border-radius: 4px;
  }

  /* chart cards — frame each chart directly (one stPlotlyChart per chart, so this
     never touches expanders/sidebar). */
  [data-testid="stPlotlyChart"] {
    background: #11161F; border: 1px solid #222A36;
    border-radius: 8px; padding: 8px 10px;
  }
  /* Streamlit paints the chart SVG with the app background (#0A0E14); clear it so
     the chart shows its #11161F card, not a darker inner rectangle. (Paper/plot are
     already transparent via chart_theme.yaml.) */
  [data-testid="stPlotlyChart"] .main-svg { background: transparent !important; }

  /* expanders ("Briefing IPCA", "Glossário", "Evidências"…) framed like the cards */
  [data-testid="stExpander"] details {
    background: #11161F; border: 1px solid #222A36 !important; border-radius: 8px;
  }
  /* popovers ("O que é cada núcleo"…) framed like the cards, with an amber info icon
     (the blue ℹ️ emoji can't be recolored via CSS, so it's drawn here instead). */
  [data-testid="stPopover"] button {
    background: #11161F !important; border: 1px solid #222A36 !important;
    border-radius: 8px; color: #E6EAF1;
  }
  [data-testid="stPopover"] button:hover { background: #161D28 !important; border-color: #2E3845 !important; }
  [data-testid="stPopover"] button::before { content: "\\24D8"; color: #E8943A; margin-right: 7px; font-weight: 600; }
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
    return json.loads(path.read_text(encoding="utf-8")).get(
        "diagnostic", "Diagnóstico indisponível."
    )


def render_top_movers(items: pd.DataFrame, date: pd.Timestamp) -> None:
    """The month's "vilões e aliados": top subitems by official 12m variation.

    The first thing a lay visitor understands in 5 seconds — names people buy
    (arroz, energia, transporte por aplicativo), not p.p. jargon. Selection is
    a pure, declared rule (transforms.top_movers); the card is silently omitted
    when the data has no usable yoy.
    """
    up, down = top_movers(items, date)
    if up.empty and down.empty:
        return

    def _rows(frame: pd.DataFrame) -> str:
        return "".join(
            "<div class='mover-row'>"
            f"<span class='mover-name'>{escape(str(row.item_name))}</span>"
            f"<span class='mover-val {'up' if row.yoy >= 0 else 'down'}'>{row.yoy:+.1f}%</span>"
            "</div>"
            for row in frame.itertuples()
        )

    st.markdown(
        "<div class='movers-grid'>"
        "<div class='movers-col'>"
        "<div class='callout-title movers-title-up'>Vilões do bolso · 12 meses</div>"
        f"{_rows(up)}</div>"
        "<div class='movers-col'>"
        "<div class='callout-title movers-title-down'>Aliados do bolso · 12 meses</div>"
        f"{_rows(down)}</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Subitens com peso ≥ 0,1% da cesta, ordenados pela variação oficial acumulada "
        "em 12 meses (IBGE/SIDRA). Regra fixa, sem curadoria manual."
    )


REPORTS_LATEST = ROOT / "reports" / "latest"


def render_ai_replay(data_month: str = "") -> None:
    """Show the pre-generated, auditable AI brief (the "Briefing IPCA").

    The brief is regenerated by the monthly refresh alongside the data. Safety net:
    if its reference month lags the data's (a rare partial-refresh failure), it is
    HIDDEN — never shown stale — and the deterministic "Leitura do mês" above
    remains current.
    """
    brief_path = REPORTS_LATEST / "ai_brief.md"
    if not brief_path.exists():
        return
    if is_stale(reference_month_from_brief(REPORTS_LATEST), data_month):
        return  # stale -> hide; the deterministic reading above carries the page
    # Open by default: the audited AI brief is the product's differentiator —
    # it must not be born hidden behind a click (spec §3.8: visible by default).
    with st.expander("Briefing IPCA", expanded=True):
        st.markdown(brief_path.read_text(encoding="utf-8"))
        meta = load_brief_metadata(REPORTS_LATEST / "metadata.json")
        if meta:
            stamp = brief_stamp_line(meta)
            if stamp:
                st.caption(
                    f"{stamp} · "
                    "[artefatos auditáveis no GitHub]"
                    "(https://github.com/Brunosavastano/OpenIPCA/tree/main/reports/latest)"
                )
    _render_brief_trace()


def _render_brief_trace() -> None:
    """The committed orchestration trace, rendered (spec_V3 §3.8).

    Sibling of the brief expander — NEVER nested inside it (Streamlit forbids
    nested expanders; see test_app_no_nested_expander). Omitted silently when
    the trace is missing or malformed.
    """
    summary = load_trace_summary(REPORTS_LATEST / "ai_trace.json")
    if summary is None:
        return
    with st.expander("Como a IA montou este brief", expanded=False):
        st.markdown(
            "A IA não escreve números por conta própria: ela consulta ferramentas "
            "determinísticas sobre os dados oficiais e cada frase é validada contra as "
            "evidências citadas — sem evidência, a frase é rejeitada (fail-closed)."
        )
        tools = ", ".join(f"`{tool}`" for tool in summary["tools"])
        st.markdown(f"**1 · Ferramentas consultadas:** {tools}")
        st.markdown(
            f"**2 · Evidências coletadas:** {summary['n_evidence']} itens, cada um com "
            "valor, unidade, data e fonte oficial."
        )
        st.markdown("**3 · Afirmações validadas pelos guardrails:**")
        for claim in summary["claims"]:
            ids = ", ".join(claim["evidence_ids"])
            st.markdown(f"- {claim['text']}" + (f"  \n  `{ids}`" if ids else ""))


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
    badge_class = {
        "critical": "crit",
        "high": "high",
        "medium": "low",
        "low": "info",
        "info": "info",
    }
    for _, row in alerts.iterrows():
        alert_id = str(row.get("alert_id", ""))
        sev = str(row.get("severity", "info"))
        text = messages.get(alert_id, "Alerta ativo sem descrição configurada.")
        sev_pt = SEVERITY_PT.get(sev, sev)
        cls = badge_class.get(sev, "info")
        # Alert text comes from our config (alert_rules.yaml), not user input.
        safe_text = escape(str(text))
        safe_sev_pt = escape(str(sev_pt))
        st.markdown(
            f"<div class='alert-box {cls}'>"
            f"<span class='badge {cls}'>{safe_sev_pt}</span>"
            f"<span class='alert-text'>{safe_text}</span></div>",
            unsafe_allow_html=True,
        )


def render_glossary() -> None:
    """A persistent, plain-language glossary for readers without macro context."""
    with st.expander("Glossário", expanded=False):
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


def prev_series_row(bcb: pd.DataFrame, name: str) -> pd.Series | None:
    """The month before the latest, for month-over-month KPI deltas."""
    subset = bcb[bcb["series_short_name"] == name].sort_values("date")
    if len(subset) < 2:
        return None
    return subset.iloc[-2]


def delta_pp(curr: float | int | None, prev: float | int | None) -> str | None:
    """Signed month-over-month change in p.p. — drives the inverted KPI arrows."""
    if curr is None or prev is None or pd.isna(curr) or pd.isna(prev):
        return None
    return f"{curr - prev:+.2f} p.p."


_KPI_NOTES = {
    "IPCA m/m": "vs. mês anterior",
    "IPCA 12m": "vs. mês anterior",
    "IPCA MM3M": "vs. mês anterior",
    "Média núcleos MM3M": "vs. mês anterior",
    "Difusão MM3M": "vs. mês anterior",
    "Alertas ativos": "",
}


def _delta_arrow(delta_text: str | None) -> tuple[str, str]:
    """(css_class, label) for an inverted KPI delta: up = bad = red, down = green.

    A change that rounds to 0.00 p.p. reads neutral (no arrow), not a red rise.
    """
    if not delta_text:
        return "flat", ""
    stripped = delta_text.lstrip()
    if stripped.startswith(("+0.00", "-0.00")):
        return "flat", ""
    if stripped[:1] == "+":
        return "up", "▲ " + delta_text
    if stripped[:1] == "-":
        return "down", "▼ " + delta_text
    return "flat", delta_text


def _kpi_tile(label_full: str, label_show: str, value: str, delta_text: str | None) -> str:
    """One KPI tile as HTML: label + (?) tooltip, mono value, plain delta, muted note."""
    cls, dlabel = _delta_arrow(delta_text)
    tip = escape(describe(label_full))
    info = f"<span class='kpi-info' title='{tip}'>?</span>" if tip else ""
    delta_html = (
        f"<div class='kpi-delta {cls}'>{escape(dlabel)}</div>"
        if dlabel
        else "<div class='kpi-delta flat'></div>"
    )
    note = escape(_KPI_NOTES.get(label_full, ""))
    note_html = f"<div class='kpi-note'>{note}</div>" if note else ""
    return (
        "<div class='kpi'>"
        f"<div class='kpi-head'><span class='kpi-label'>{escape(label_show)}</span>{info}</div>"
        f"<div class='kpi-value'>{escape(value)}</div>"
        f"{delta_html}{note_html}"
        "</div>"
    )


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
    ipca_prev = prev_series_row(bcb, "IPCA")
    diffusion_prev = prev_series_row(bcb, "Difusao")
    core_prev_df = cores[
        (cores["core_set_name"] == "bcb_compact")
        & (cores["core_name"].isin(["Media", "Média"]))
        & (cores["date"] < latest_date)
    ].sort_values("date")
    core_prev = core_prev_df.iloc[-1] if not core_prev_df.empty else None

    st.title("OpenIPCA — Painel executivo")
    st.caption(f"Último dado processado: {latest_date:%Y-%m} | Fontes: BCB/SGS e IBGE/SIDRA")

    notice = freshness_notice()
    if notice is not None:
        severity, details = notice
        (st.error if severity == "block" else st.warning)(f"Freshness: {details}")

    # KPI tiles as a custom HTML grid: st.metric can't carry the "vs. mês anterior"
    # note nor keep the delta-less "Alertas" tile the same height. Inverted delta
    # (up = bad = red, down = green) is reproduced by _delta_arrow.
    ipca_mom = ipca["mom"] if ipca is not None else None
    ipca_12m = ipca["rolling_12m"] if ipca is not None else None
    ipca_mm3m = ipca["moving_average_3m"] if ipca is not None else None
    core_mm3m = core_row["moving_average_3m"] if core_row is not None else None
    diff_mm3m = diffusion["moving_average_3m"] if diffusion is not None else None

    tiles = [
        _kpi_tile(
            "IPCA m/m",
            "IPCA m/m",
            fmt(ipca_mom),
            delta_pp(ipca_mom, ipca_prev["mom"] if ipca_prev is not None else None),
        ),
        _kpi_tile(
            "IPCA 12m",
            "IPCA 12m",
            fmt(ipca_12m),
            delta_pp(ipca_12m, ipca_prev["rolling_12m"] if ipca_prev is not None else None),
        ),
        _kpi_tile(
            "IPCA MM3M",
            "IPCA MM3M",
            fmt(ipca_mm3m),
            delta_pp(ipca_mm3m, ipca_prev["moving_average_3m"] if ipca_prev is not None else None),
        ),
        _kpi_tile(
            "Média núcleos MM3M",
            "Núcleos MM3M",
            fmt(core_mm3m),
            delta_pp(core_mm3m, core_prev["moving_average_3m"] if core_prev is not None else None),
        ),
        _kpi_tile(
            "Difusão MM3M",
            "Difusão MM3M",
            fmt(diff_mm3m),
            delta_pp(
                diff_mm3m,
                diffusion_prev["moving_average_3m"] if diffusion_prev is not None else None,
            ),
        ),
        _kpi_tile("Alertas ativos", "Alertas ativos", str(len(alerts)), None),
    ]
    st.markdown(f"<div class='kpi-grid'>{''.join(tiles)}</div>", unsafe_allow_html=True)

    regime = classify_latest_regime(bcb)
    st.markdown(
        "<div class='regime-row'><span class='regime-key'>Regime inflacionário:</span>"
        f"<span class='regime-pill'>{escape(regime.label_pt.upper())}</span></div>",
        unsafe_allow_html=True,
    )
    regime_explanation = describe(regime.label_pt)
    if regime_explanation:
        st.caption(regime_explanation)

    st.markdown(
        "<div class='diagnostic'><div class='callout-title info'>Leitura do mês</div>"
        f"{escape(load_diagnostic())}</div>",
        unsafe_allow_html=True,
    )

    render_top_movers(items, latest_date)

    with st.container(border=True):
        st.markdown(
            "<span class='ask-cta'></span>"
            "<div class='callout-title cta'>Pergunte ao IPCA</div>"
            "Faça uma pergunta em português sobre a inflação e receba uma resposta "
            "aterrada nos dados oficiais — cada número rastreável a uma evidência.",
            unsafe_allow_html=True,
        )
        if st.button("Abrir Pergunte ao IPCA", key="open_ask"):
            st.session_state["goto_ask"] = True
            st.rerun()

    render_ai_replay(f"{latest_date:%Y-%m}")
    render_glossary()

    left, right = st.columns([1.25, 1])
    with left:
        st.plotly_chart(stacked_contribution(items), use_container_width=True)
    with right:
        st.plotly_chart(diffusion_line(bcb), use_container_width=True)
    st.plotly_chart(core_lines(cores, "bcb_compact", "moving_average_3m"), use_container_width=True)

    render_active_alerts(alerts)


def render_drilldown(items: pd.DataFrame, date: pd.Timestamp) -> None:
    """Navigate the hierarchy: group → subgroup → item → subitem.

    Answers 'which subitems make up an item?' using the parent/child links
    already in the data. Each step shows the children ordered by contribution.
    """
    st.subheader("Composição: do grupo ao subitem")
    st.caption(
        "Escolha um grupo e desça nos níveis para ver de que ele é feito. "
        "O IPCA se organiza em grupo → subgrupo → item → subitem."
    )

    groups = top_level_rows(items, date)
    if groups.empty:
        st.info("Sem dados de composição para o mês selecionado.")
        return

    # Selected path of classification codes, one per level (built via selectboxes).
    def _pick(level_rows: pd.DataFrame, level: str, key: str) -> pd.Series | None:
        if level_rows.empty:
            return None
        options = list(level_rows["classification_code"])
        labels = {
            r["classification_code"]: f"{r['item_name']} ({r['contribution_mom']:.2f} p.p.)"
            for _, r in level_rows.iterrows()
        }
        chosen = st.selectbox(
            LEVEL_LABEL_PT.get(level, level),
            options,
            format_func=lambda c: labels.get(c, c),
            key=key,
        )
        return level_rows[level_rows["classification_code"] == chosen].iloc[0]

    crumbs: list[str] = []
    group_row = _pick(groups, "group", "dd_group")
    if group_row is not None:
        crumbs.append(group_row["item_name"])
        subgroups = children(items, group_row["classification_code"], date)
        sub_row = _pick(subgroups, "subgroup", "dd_subgroup") if not subgroups.empty else None
        if sub_row is not None:
            crumbs.append(sub_row["item_name"])
            sub_items = children(items, sub_row["classification_code"], date)
            item_row = _pick(sub_items, "item", "dd_item") if not sub_items.empty else None
            current = item_row if item_row is not None else sub_row
        else:
            current = group_row
        # Show the children of whatever node is currently selected (deepest picked).
        st.markdown("**" + " › ".join(crumbs) + "**")
        kids = children(items, current["classification_code"], date)
        if kids.empty:
            st.caption(f"{current['item_name']} não tem subdivisão neste nível.")
        else:
            label = node_label(items, current["classification_code"], date)
            st.markdown(
                f"{label} (variou {current['mom']:.2f}%, "
                f"contribuiu {current['contribution_mom']:.2f} p.p.) é composto por:"
            )
            show = kids[["item_name", "mom", "contribution_mom", "weight"]].rename(
                columns={
                    "item_name": "Componente",
                    "mom": "Variação (%)",
                    "contribution_mom": "Contribuição (p.p.)",
                    "weight": "Peso (%)",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)


def page_decomposition(data: dict[str, pd.DataFrame]) -> None:
    items = data["items"]
    st.header("Decomposição do IPCA")
    st.caption(
        "**Variação (%)** = quanto o preço do grupo mudou no mês (é o número do "
        "IBGE/SIDRA). **Contribuição (p.p.)** = quanto ele puxou do IPCA do mês "
        "= variação × peso ÷ 100. Um item pode variar muito e contribuir pouco se "
        "seu peso na cesta for pequeno."
    )
    dates = sorted(pd.to_datetime(items["date"]).dropna().unique())
    selected_date = st.selectbox(
        "Mês de referência",
        dates,
        index=len(dates) - 1,
        format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m"),
    )
    selected_date = pd.Timestamp(selected_date)
    level = st.selectbox(
        "Nível de detalhe (ranking e download)",
        ["group", "subgroup", "item", "subitem"],
        index=3,
        format_func=lambda lv: LEVEL_LABEL_PT.get(lv, lv),
    )

    # Time-series charts (always last 24 months — independent of the month picker).
    st.plotly_chart(stacked_contribution(items), use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.caption(f"Waterfall e ranking referem-se a {selected_date:%Y-%m}.")
        st.plotly_chart(waterfall_latest(items, selected_date), use_container_width=True)
    with right:
        st.caption("Maiores altas e baixas no nível de detalhe selecionado.")
        st.plotly_chart(contribution_ranking(items, selected_date, level), use_container_width=True)
    st.plotly_chart(heatmap_groups(items), use_container_width=True)

    render_drilldown(items, selected_date)

    latest = items[(items["date"] == selected_date) & (items["level"] == level)].copy()
    st.download_button(
        f"Baixar dados ({LEVEL_LABEL_PT.get(level, level)}) — CSV",
        latest.sort_values("contribution_mom", ascending=False).to_csv(index=False).encode("utf-8"),
        file_name=f"ranking_{level}_{selected_date:%Y_%m}.csv",
        mime="text/csv",
    )


def page_cores(data: dict[str, pd.DataFrame]) -> None:
    cores = data["cores"]
    core_sets = load_yaml("core_sets.yaml").get("core_sets", {})
    labels = {key: value.get("label", key) for key, value in core_sets.items()}
    selected = st.selectbox(
        "Conjunto de núcleos", list(labels), format_func=lambda key: labels[key]
    )

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
                    f"Conjunto incompleto no mês mais recente: {avail}/{exp} séries disponíveis. "
                    f"Faltando: {missing}. A média é omitida quando o conjunto está incompleto."
                )

    st.header("Monitor de núcleos")
    # What "núcleos" are, then a legend for the cores in the selected conjunto.
    st.caption(describe("nucleos"))
    members = core_sets.get(selected, {}).get("members", [])
    if members:
        legend = "  \n".join(f"- {describe(m)}" for m in members if describe(m))
        if legend:
            with st.popover("O que é cada núcleo"):
                st.markdown(legend)

    # Metric selector reuses the single-source METRIC_LABELS (same labels the
    # chart titles use, so they never diverge). Default to MM3M.
    metric_options = [m for m in ("moving_average_3m", "rolling_12m", "mom", "three_month_saar")]
    metric = st.selectbox(
        "Métrica",
        metric_options,
        index=0,
        format_func=lambda key: METRIC_LABELS.get(key, key),
    )
    st.caption("Momentum sem ajuste sazonal (NSA). Versão com ajuste sazonal (SA) chega no v0.2.")
    st.plotly_chart(core_lines(cores, selected, metric), use_container_width=True)
    st.plotly_chart(core_fan(cores, selected, metric), use_container_width=True)

    # Numeric detail behind a toggle: clean headers, useful columns only.
    with st.expander("Ver tabela de núcleos (detalhe)", expanded=False):
        st.caption("Valores mais recentes de cada núcleo do conjunto.")
        latest = (
            cores[cores["core_set_name"] == selected]
            .sort_values("date")
            .groupby("core_name")
            .tail(1)
            .sort_values("moving_average_3m", ascending=False)
        )
        rename = {
            "core_name": "Núcleo",
            "mom": "No mês (%)",
            "moving_average_3m": "MM3M (%)",
            "rolling_12m": "12m (%)",
        }
        cols = [c for c in rename if c in latest.columns]
        st.dataframe(
            latest[cols].rename(columns=rename),
            use_container_width=True,
            hide_index=True,
        )


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

        **Núcleos.** A média dos núcleos é calculada a partir do conjunto selecionado em `config/core_sets.yaml`.

        **Alertas.** Regras declarativas em `config/alert_rules.yaml`; o dashboard exibe apenas os
        alertas disparados no último processamento.

        **Validação.** O pipeline checa duplicidades, faixas plausíveis, disponibilidade do conjunto
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


# (css class, short uppercase label, explanation) for the answer's mode seal —
# a sober mono pill with a colored dot instead of an emoji.
_ASK_SEAL = {
    "ai": ("live", "AO VIVO", "Resposta gerada ao vivo, aterrada nos dados oficiais."),
    "replay": ("", "PRÉ-GERADA", "Resposta pré-gerada e auditada (IA ao vivo indisponível agora)."),
    "fallback": ("", "INDISPONÍVEL", "A IA está indisponível no momento — use o painel e o brief."),
    "deterministic": (
        "",
        "INDISPONÍVEL",
        "A IA está indisponível no momento — use o painel e o brief.",
    ),
    "refused": (
        "refused",
        "RECUSADA",
        "Fora do escopo (apenas inflação/IPCA) ou recusada por segurança.",
    ),
}


def page_ask(data: dict[str, pd.DataFrame]) -> None:
    bcb, items, cores, alerts = data["bcb"], data["items"], data["cores"], data["alerts"]
    st.title("Pergunte ao IPCA")
    st.caption(
        "Pergunte em português sobre a inflação brasileira. A resposta é aterrada nos "
        "dados oficiais já calculados — cada número é rastreável a uma evidência. Com uma "
        "chave de IA configurada, a resposta é gerada ao vivo; caso contrário, mostramos "
        "uma resposta pré-gerada e auditada. A IA nunca dá recomendação de investimento "
        "nem previsão de Copom/Selic."
    )

    st.markdown("**Perguntas para começar:**")
    cols = st.columns(2)
    for index, question in enumerate(CURATED_QUESTIONS):
        if cols[index % 2].button(question, key=f"ask_sugg_{index}", use_container_width=True):
            st.session_state["qa_last_q"] = question

    typed = st.text_input(
        "Ou escreva a sua pergunta:",
        key="qa_input",
        placeholder="Ex.: O que puxou a inflação do mês?",
    )
    if st.button("Perguntar", key="qa_submit", type="primary") and typed.strip():
        st.session_state["qa_last_q"] = typed.strip()

    question = st.session_state.get("qa_last_q")
    if not question:
        st.info("Escolha uma pergunta acima ou escreva a sua para começar.")
        return

    # Cache the answer for the current question: Streamlit reruns on every widget
    # interaction, and without this each rerun would re-hit the live model — wasted
    # quota on a public box with no rate-limit. Only call when the question changes.
    cache = st.session_state.get("qa_cache")
    if cache is None or cache.get("q") != question:
        with st.spinner("Consultando os dados do IPCA..."):
            result = answer_with_replay(question, bcb, items, cores, alerts)
        st.session_state["qa_cache"] = {"q": question, "result": result}
    result = st.session_state["qa_cache"]["result"]

    st.markdown(f"**Você perguntou:** {question}")
    seal_cls, seal_label, seal_note = _ASK_SEAL.get(result.mode, ("", "", ""))
    if seal_label:
        safe_cls = escape(seal_cls, quote=True)
        safe_label = escape(seal_label)
        safe_note = escape(seal_note)
        st.markdown(
            f"<span class='mode-seal {safe_cls}'>● {safe_label}</span> "
            f"&nbsp;<span class='small-note'>{safe_note}</span>",
            unsafe_allow_html=True,
        )
    # No unsafe_allow_html here: the model's prose is rendered as inert text so a
    # crafted answer can never inject HTML into the public page.
    st.markdown(result.answer)

    if result.claims:
        with st.expander("🔎 Evidências — cada número rastreado a um dado oficial", expanded=False):
            # Resolved table (metric/value/source), not raw evidence_ids: the id
            # alone is unreadable; the promise is auditable BY HUMANS.
            rows = resolve_claim_evidence(result.claims, result.evidence)
            if rows:
                st.dataframe(
                    pd.DataFrame(rows).rename(
                        columns={
                            "claim": "Afirmação",
                            "metric": "Métrica",
                            "value": "Valor",
                            "unit": "Unidade",
                            "date": "Data",
                            "source": "Fonte",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )


_PT_MONTHS = {
    1: "JAN", 2: "FEV", 3: "MAR", 4: "ABR", 5: "MAI", 6: "JUN",
    7: "JUL", 8: "AGO", 9: "SET", 10: "OUT", 11: "NOV", 12: "DEZ",
}


def _status_strip_right(data: dict[str, pd.DataFrame]) -> str:
    """Freshness + quality seal for the strip: 'DADOS ABR/2026 · 8/8 VERIFICAÇÕES OK'.

    Answers the first question any data-dashboard visitor has ("isso é de
    quando?") and surfaces the validation rigor that already runs every month.
    Only our own derived values go in (months/counts) — no user input.
    """
    parts: list[str] = []
    try:
        latest = pd.to_datetime(data["bcb"]["date"]).max()
        if pd.notna(latest):
            parts.append(f"DADOS {_PT_MONTHS[latest.month]}/{latest.year}")
    except (KeyError, TypeError, ValueError):
        pass  # the strip must never break the app
    summary = summarize_report(OUTPUTS_DIR / "validation_report.csv")
    if summary:
        seal_cls = {"pass": "seal-ok", "warn": "seal-warn", "block": "seal-block"}[
            str(summary["worst"])
        ]
        label = f"{summary['passed']}/{summary['total']} VERIFICAÇÕES"
        if summary["worst"] == "pass":
            label += " OK"
        parts.append(f"<span class='{seal_cls}'>{label}</span>")
    return " · ".join(parts) or "openipca.streamlit.app"


def main() -> None:
    try:
        data = load_data(processed_signature())
    except FileNotFoundError as exc:
        st.title("OpenIPCA")
        st.error("Dados processados não encontrados.")
        st.code("python -m ipca_dashboard.pipeline run\nstreamlit run dashboard/app.py")
        st.caption(str(exc))
        return

    # "Abrir Pergunte ao IPCA" (a button on the panel) routes here: promote its flag to
    # the nav radio's value BEFORE the radio is instantiated, so it renders pre-selected.
    if st.session_state.pop("goto_ask", False):
        st.session_state["nav_page"] = "Pergunte ao IPCA"

    st.sidebar.markdown(
        "<div class='brand'><span class='brand-mark'>I</span>"
        "<span class='brand-name'>Open<span class='brand-accent'>IPCA</span></span></div>"
        "<div class='nav-label'>Navegação</div>",
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        "Navegação",
        [
            "Painel executivo",
            "Pergunte ao IPCA",
            "Decomposição",
            "Núcleos",
            "Difusão",
            "Alertas",
            "Metodologia",
        ],
        key="nav_page",
        label_visibility="collapsed",
    )
    st.markdown(
        "<div class='status-strip'>"
        f"<span class='strip-left'><span class='dot'></span>{escape(page.upper())}</span>"
        f"<span class='strip-right'>{_status_strip_right(data)}</span></div>",
        unsafe_allow_html=True,
    )
    if page == "Painel executivo":
        page_executive(data)
    elif page == "Pergunte ao IPCA":
        page_ask(data)
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
