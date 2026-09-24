from __future__ import annotations

import json
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ipca_dashboard.ai.english import CURATED_QUESTIONS  # noqa: E402
from ipca_dashboard.ai.env import bridge_secrets_to_env, load_env_once  # noqa: E402
from ipca_dashboard.ai.evidence import resolve_claim_evidence  # noqa: E402
from ipca_dashboard.ai.qa import answer_question  # noqa: E402
from ipca_dashboard.ai.staleness import (  # noqa: E402
    is_stale,
    normalize_analysis_title,
    reference_month_from_brief,
)
from ipca_dashboard.ai.trace import (  # noqa: E402
    brief_stamp_line,
    load_brief_metadata,
    load_trace_summary,
)
from ipca_dashboard.buildinfo import build_stamp  # noqa: E402
from ipca_dashboard.charts import (  # noqa: E402
    contribution_ranking,
    core_fan,
    core_lines,
    diffusion_line,
    heatmap_groups,
    ipca_diffusion_scatter,
    momentum_line,
    stacked_contribution,
    subitem_sparkline,
    waterfall_latest,
)
from ipca_dashboard.config import OUTPUTS_DIR, PROCESSED_DIR, load_yaml  # noqa: E402
from ipca_dashboard.diagnostics import classify_latest_regime  # noqa: E402
from ipca_dashboard.english import (  # noqa: E402
    LEVEL_LABEL_PT,
    METHODOLOGY_EN,
    display_data,
    english_diagnostic,
    translate_text,
)
from ipca_dashboard.glossary_en import (  # noqa: E402
    CONCEPTS,
    CORE_TERMS,
    METRIC_LABELS,
    REGIME_LABELS,  # noqa: E402
    SEVERITY_PT,
    describe,
)
from ipca_dashboard.hierarchy import (  # noqa: E402
    children,
    node_label,
    subitem_options,
    top_level_rows,
)
from ipca_dashboard.navigation import (  # noqa: E402
    PAGE_SLUGS,
    SLUG_BY_PAGE,
    NavigationTarget,
    parse_query_params,
    target_for_evidence,
)
from ipca_dashboard.release import freshness_status as release_freshness_status  # noqa: E402
from ipca_dashboard.release import load_release_state as read_release_state  # noqa: E402
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
    page_title="OpenIPCA — Brazilian inflation beyond the headline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="auto",
)


CSS = """
<style>
  /* Institutional "terminal" theme (Bloomberg/Aladdin direction). IBM Plex Sans
     for UI, IBM Plex Mono (tabular) for numbers. Coherent with config.toml. */
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

  html, body, [class*="css"], .stApp { font-family: 'IBM Plex Sans', sans-serif; }
  .main .block-container { padding-top: 1.4rem; max-width: 1400px; }
  h1 { font-size: 1.55rem; font-weight: 600; letter-spacing: 0; color: #E6EAF1; }
  h2, h3 { font-weight: 600; color: #E6EAF1; letter-spacing: 0; }
  [data-testid="stCaptionContainer"], .small-note { color: #8A93A3; }

  /* sidebar */
  [data-testid="stSidebar"] { background: #11161F; border-right: 1px solid #222A36; }

  /* KPI tiles — custom grid (st.markdown HTML). Equal height via the grid; each
     tile = label + (?) tooltip, mono value, plain colored delta, muted note. */
  .kpi-grid {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
    grid-auto-rows: 1fr; gap: 10px; margin: 2px 0 6px;
  }
  @media (max-width: 760px)  { .kpi-grid { grid-template-columns: 1fr; } }
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

  /* Compact secondary metrics: subordinate to the three headline KPIs. */
  .secondary-strip {
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    border-top: 1px solid #222A36; border-bottom: 1px solid #222A36;
    margin: 12px 0 18px;
  }
  .secondary-metric { padding: 10px 14px; border-right: 1px solid #222A36; min-width: 0; }
  .secondary-metric:last-child { border-right: 0; }
  .secondary-label {
    color: #5A6373; font: 500 .62rem 'IBM Plex Mono', monospace;
    letter-spacing: .08em; text-transform: uppercase;
  }
  .secondary-value {
    color: #B7BECB; font: 500 1rem 'IBM Plex Mono', monospace; margin-top: 3px;
  }
  @media (max-width: 760px) {
    .secondary-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .secondary-metric:nth-child(2) { border-right: 0; }
  }

  /* Release status and the signature analytical ruler are full-width bands, not cards. */
  .release-status {
    display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
    border-top: 1px solid #222A36; border-bottom: 1px solid #222A36;
    margin: 10px 0 18px;
  }
  .release-status-cell { padding: 11px 14px; border-right: 1px solid #222A36; min-width: 0; }
  .release-status-cell:last-child { border-right: 0; }
  .release-status-key {
    color: #5A6373; font: 500 .6rem 'IBM Plex Mono', monospace;
    letter-spacing: .1em; text-transform: uppercase;
  }
  .release-status-value { color: #E6EAF1; font-size: .88rem; font-weight: 600; margin-top: 4px; }
  .release-status-note { color: #8A93A3; font-size: .7rem; margin-top: 2px; }
  .release-status-value.ok { color: #35B07D; }
  .release-status-value.warn { color: #E0A046; }
  .release-status-value.block { color: #E5484D; }

  .release-ruler {
    display: grid; grid-template-columns: 1fr 1.35fr 1fr 1fr 1fr;
    border-top: 1px solid #2E3845; border-bottom: 1px solid #2E3845;
    margin: 16px 0 18px;
  }
  .release-stage { padding: 13px 14px; border-right: 1px solid #222A36; min-width: 0; }
  .release-stage:last-child { border-right: 0; }
  .release-stage-key {
    color: #E8943A; font: 600 .6rem 'IBM Plex Mono', monospace;
    letter-spacing: .11em; text-transform: uppercase;
  }
  .release-stage-value { color: #E6EAF1; font-size: .9rem; font-weight: 600; margin-top: 5px; }
  .release-stage-note { color: #8A93A3; font-size: .72rem; line-height: 1.35; margin-top: 3px; }
  @media (max-width: 900px) {
    .release-ruler { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .release-stage:nth-child(2n) { border-right: 0; }
  }
  @media (max-width: 640px) {
    .release-status, .release-ruler, .secondary-strip { grid-template-columns: 1fr; }
    .release-status-cell, .release-stage, .secondary-metric {
      border-right: 0; border-bottom: 1px solid #222A36;
    }
    .release-status-cell:last-child, .release-stage:last-child, .secondary-metric:last-child {
      border-bottom: 0;
    }
  }

  /* "Vilões e aliados" — monthly ranking with 12m context, in everyday names */
  .movers-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 2px 0 6px; }
  @media (max-width: 640px) { .movers-grid { grid-template-columns: 1fr; } }
  .movers-col {
    background: #11161F; border: 1px solid #222A36; border-radius: 6px; padding: 12px 14px;
  }
  .movers-title-up { color: #E5484D; }
  .movers-title-down { color: #35B07D; }
  .mover-row {
    display: grid; grid-template-columns: minmax(0, 1fr) 68px 76px;
    align-items: baseline; column-gap: 10px; padding: 4px 0;
  }
  .mover-head {
    border-bottom: 1px solid #222A36; margin: 3px 0 4px; padding-bottom: 6px;
    color: #697386; font: 500 .58rem 'IBM Plex Mono', monospace;
    letter-spacing: .08em; text-transform: uppercase;
  }
  .mover-sort-label {
    display: inline-flex; align-items: center; justify-content: flex-end; gap: 5px;
    color: #697386;
    border-bottom: 1px solid transparent; padding-bottom: 2px;
  }
  .mover-sort-label.active {
    color: #E8943A; border-color: #E8943A; font-weight: 700;
  }
  .mover-sort-mark { font-size: .48rem; line-height: 1; }
  .mover-name {
    color: #E6EAF1; font-size: .86rem;
    min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .mover-val {
    font-family: 'IBM Plex Mono', monospace; font-size: .82rem;
    font-variant-numeric: tabular-nums; text-align: right;
  }
  .mover-val.up { color: #E5484D; }
  .mover-val.down { color: #35B07D; }
  .mover-val.flat, .mover-val.na { color: #697386; }
  .mover-val-month { font-weight: 700; }
  .mover-val-yoy { font-weight: 400; opacity: .74; }
  .mover-empty { color: #697386; font-size: .78rem; padding: 8px 0 3px; }
  @media (max-width: 420px) {
    .mover-row { grid-template-columns: minmax(0, 1fr) 62px 70px; column-gap: 7px; }
    .mover-name, .mover-val { font-size: .76rem; }
  }

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
  /* selectboxes ("Core set", "Metric"…) framed like the cards */
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
  /* "Ask the IPCA" CTA: a bordered container (so the button sits inside the box),
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
  [data-testid="stSidebar"] .brand-name { font-weight: 600; font-size: 1.05rem; color: #E6EAF1; letter-spacing: 0; }
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
  @media (max-width: 640px) {
    .status-strip { align-items: flex-start; flex-direction: column; gap: 5px; }
    .status-strip .strip-right { line-height: 1.5; }
  }

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

  /* expanders ("OpenIPCA analysis", "Glossary", "Evidences"…) framed like the cards */
  [data-testid="stExpander"] details {
    background: #11161F; border: 1px solid #222A36 !important; border-radius: 8px;
  }
  /* popovers ("What each core measure means"…) framed like the cards, with an amber info icon
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
RELEASE_STATE_PATH = OUTPUTS_DIR / "release_state.json"


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
        return "Analysis not yet generated."
    return json.loads(path.read_text(encoding="utf-8")).get(
        "diagnostic", "Analysis unavailable."
    )


def _set_query_params(**updates: str) -> None:
    """Update only validated public parameters without disturbing unrelated state."""
    try:
        current = {key: str(value) for key, value in st.query_params.items()}
        for key, value in updates.items():
            if value:
                current[key] = value
            else:
                current.pop(key, None)
        if current != {key: str(value) for key, value in st.query_params.items()}:
            st.query_params.from_dict(current)
    except Exception:  # noqa: BLE001 - old/mocked Streamlit must still render
        return


def _apply_query_params_once() -> None:
    if st.session_state.get("query_params_applied"):
        return
    try:
        target = parse_query_params(st.query_params)
    except Exception:  # noqa: BLE001 - malformed public URL must never break the app
        target = NavigationTarget("")
    if target.view:
        st.session_state["nav_page"] = PAGE_SLUGS[target.view]
    if target.month:
        st.session_state["nav_month"] = target.month
    if target.item:
        st.session_state["nav_item"] = target.item
    st.session_state["query_params_applied"] = True


def _navigate_to_target(target: NavigationTarget) -> None:
    st.session_state["pending_navigation"] = {
        "view": target.view,
        "month": target.month,
        "item": target.item,
    }
    _set_query_params(
        view=target.view,
        month=target.month,
        evidence=target.evidence,
        item=target.item,
    )
    st.rerun()


def _format_release_date(value: object) -> str:
    try:
        return date.fromisoformat(str(value)).strftime("%d %b %Y")
    except ValueError:
        return "not reported"


def _format_build_time(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d %b %Y %H:%M UTC")
    except ValueError:
        return "time not reported"


def render_release_status(data: dict[str, pd.DataFrame]) -> None:
    """Separate data recency, strict integrity and the next official calendar date."""
    state = read_release_state(RELEASE_STATE_PATH)
    try:
        data_month = pd.to_datetime(data["bcb"]["date"]).max().strftime("%Y-%m")
    except (AttributeError, KeyError, TypeError, ValueError):
        data_month = ""
    month = data_month or str(state.get("reference_month", ""))
    summary = summarize_report(OUTPUTS_DIR / "validation_report.csv")
    if summary:
        quality = f"{summary['passed']}/{summary['total']} checks"
        quality_class = {"pass": "ok", "warn": "warn", "block": "block"}[
            str(summary["worst"])
        ]
        quality_note = "strict checks passed" if summary["worst"] == "pass" else "view details"
    else:
        quality, quality_class, quality_note = "not reported", "warn", "no report"
    freshness = release_freshness_status(state)
    next_note = {
        "current": "official calendar",
        "due_today": "release expected today",
        "overdue": "a new release was expected",
        "unknown": "calendar unavailable",
    }[freshness]
    next_class = "warn" if freshness in {"due_today", "overdue", "unknown"} else ""
    try:
        year, month_number = (int(part) for part in month.split("-"))
        month_label = f"{_PT_MONTHS[month_number]}/{year}"
    except (KeyError, ValueError):
        month_label = "not reported"
    st.markdown(
        "<div class='release-status'>"
        "<div class='release-status-cell'>"
        "<div class='release-status-key'>Latest data</div>"
        f"<div class='release-status-value'>{escape(month_label)}</div>"
        f"<div class='release-status-note'>build {_format_build_time(state.get('built_at'))}</div>"
        "</div>"
        "<div class='release-status-cell'>"
        "<div class='release-status-key'>Data integrity</div>"
        f"<div class='release-status-value {quality_class}'>{escape(quality)}</div>"
        f"<div class='release-status-note'>{escape(quality_note)}</div>"
        "</div>"
        "<div class='release-status-cell'>"
        "<div class='release-status-key'>Next release</div>"
        f"<div class='release-status-value {next_class}'>"
        f"{escape(_format_release_date(state.get('next_release_date')))}</div>"
        f"<div class='release-status-note'>{escape(next_note)}</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    if state and state.get("reference_month") != data_month:
        st.warning("Release metadata do not match the reference month of the data files.")
    elif freshness == "overdue":
        st.warning(
            "The next release was already expected according to the official calendar. "
            "The dashboard retains the latest validated dataset while the refresh is reprocessed."
        )
    elif freshness == "due_today":
        st.info(
            "A release is expected today. The detector publishes once SIDRA and the critical "
            "BCB series are complete."
        )


@st.fragment
def render_top_movers(items: pd.DataFrame, date: pd.Timestamp) -> None:
    """"Vilões e aliados" ranked by the official variation selected in the header.

    The first thing a lay visitor understands in 5 seconds — names people buy
    (arroz, energia, transporte por aplicativo), not p.p. jargon. The visitor can
    switch between monthly and 12-month ranking without losing either value.
    """
    rank_by = st.segmented_control(
        "Rank by",
        options=["mom", "yoy"],
        default="mom",
        format_func=lambda value: "Month" if value == "mom" else "12 months",
        key="top_movers_rank",
        help="The selected period determines the ranking and the split between increases and decreases.",
    )
    rank_by = str(rank_by) if rank_by in {"mom", "yoy"} else "mom"

    all_up, all_down = top_movers(items, date, n=None, rank_by=rank_by)
    if all_up.empty and all_down.empty:
        return

    show_all = st.toggle(
        "Show all eligible subitems",
        value=False,
        key="show_all_top_movers",
        help="Expands the ranking beyond the top five on each side.",
    )
    up = all_up if show_all else all_up.head(5)
    down = all_down if show_all else all_down.head(5)
    if up.empty and down.empty:
        return

    def _value_class(value: object) -> str:
        if pd.isna(value):
            return "na"
        numeric = float(value)
        return "up" if numeric > 0 else "down" if numeric < 0 else "flat"

    def _format_change(value: object) -> str:
        return "n/a" if pd.isna(value) else f"{float(value):+.1f}%"

    def _rows(frame: pd.DataFrame) -> str:
        if frame.empty:
            return "<div class='mover-empty'>No eligible subitems this month.</div>"
        return "".join(
            "<div class='mover-row'>"
            f"<span class='mover-name'>{escape(str(row.item_name))}</span>"
            f"<span class='mover-val mover-val-month {_value_class(row.mom)}'>"
            f"{_format_change(row.mom)}</span>"
            f"<span class='mover-val mover-val-yoy {_value_class(row.yoy)}'>"
            f"{_format_change(row.yoy)}</span>"
            "</div>"
            for row in frame.itertuples()
        )

    def _sort_label(label: str, value: str) -> str:
        active = rank_by == value
        active_class = " active" if active else ""
        marker = "<span class='mover-sort-mark' aria-hidden='true'>●</span>" if active else ""
        return (
            f"<span class='mover-sort-label{active_class}'>{label}{marker}</span>"
        )

    header = (
        "<div class='mover-row mover-head'>"
        "<span>Subitem</span>"
        f"{_sort_label('Month', 'mom')}"
        f"{_sort_label('12 months', 'yoy')}"
        "</div>"
    )
    period_title = "this month" if rank_by == "mom" else "over 12 months"
    ranking_description = (
        "monthly change" if rank_by == "mom" else "12-month cumulative change"
    )
    st.markdown(
        "<div id='ranking-movers' class='movers-grid'>"
        "<div class='movers-col'>"
        f"<div class='callout-title movers-title-up'>Largest price increases · {period_title}</div>"
        f"{header}{_rows(up)}</div>"
        "<div class='movers-col'>"
        f"<div class='callout-title movers-title-down'>Largest price decreases · {period_title}</div>"
        f"{header}{_rows(down)}</div></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        f"Ranked by {ranking_description}; use the selector above to reorder. "
        "Subitems with a basket weight of at least 0.1% (IBGE/SIDRA), with no manual selection."
    )


REPORTS_LATEST = ROOT / "reports" / "latest"


def render_ai_replay(data_month: str = "") -> None:
    """Show the pre-generated, auditable monthly analysis.

    The brief is regenerated by the monthly refresh alongside the data. Safety net:
    if its reference month lags the data's (a rare partial-refresh failure), it is
    HIDDEN — never shown stale — and the deterministic "Monthly analysis" above
    remains current.
    """
    brief_path = REPORTS_LATEST / "ai_brief.md"
    if not brief_path.exists():
        return
    if is_stale(reference_month_from_brief(REPORTS_LATEST), data_month):
        return  # stale -> hide; the deterministic reading above carries the page
    meta = load_brief_metadata(REPORTS_LATEST / "metadata.json") or {}
    if meta.get("language") != "en":
        # Keep source archives accessible without replacing the current English analysis.
        with st.expander("Source report archive (Portuguese)", expanded=False):
            st.markdown(
                "[Read the original report and its evidence on GitHub]"
                "(https://github.com/Brunosavastano/OpenIPCA/tree/main/reports/latest)"
            )
        return
    # Open by default: the audited analysis is the product's differentiator —
    # it must not be born hidden behind a click (spec §3.8: visible by default).
    with st.expander("OpenIPCA analysis", expanded=True):
        st.caption("Based on official data · traceable to evidence")
        st.markdown(normalize_analysis_title(brief_path.read_text(encoding="utf-8")))
        meta = load_brief_metadata(REPORTS_LATEST / "metadata.json")
        if meta:
            stamp = brief_stamp_line(meta)
            if stamp:
                st.caption(
                    f"{stamp} · "
                    "[auditable artifacts on GitHub]"
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
    with st.expander("How this analysis was built", expanded=False):
        st.markdown(
            "AI does not invent numbers: it queries deterministic tools "
            "over official data. Every claim is checked against its cited "
            "evidence; claims without evidence are rejected."
        )
        tools = ", ".join(f"`{tool}`" for tool in summary["tools"])
        st.markdown(f"**1 · Tools consulted:** {tools}")
        st.markdown(
            f"**2 · Evidence collected:** {summary['n_evidence']} items, each with "
            "a value, unit, date and official source."
        )
        st.markdown("**3 · Claims validated against evidence:**")
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
    st.subheader("Active alerts")
    st.caption(describe("alertas"))
    if alerts.empty:
        st.info("No active alerts this month.")
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
        text = translate_text(messages.get(alert_id, "Active alert with no configured description."))
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
    with st.expander("Glossary", expanded=False):
        for text in CONCEPTS.values():
            st.markdown(f"- {text}")
        st.markdown("**IPCA core measures:**")
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
        return "n/a"
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
    "IPCA m/m": "vs. previous month",
    "IPCA 12m": "vs. previous month",
    "IPCA 3M average": "vs. previous month",
    "IPCA 3M annualized SA": "vs. previous month",
    "Core mean, 3M average": "vs. previous month",
    "Diffusion 3M average": "vs. previous month",
    "Active alerts": "",
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


def _secondary_metric(label: str, value: str) -> str:
    return (
        "<div class='secondary-metric'>"
        f"<div class='secondary-label'>{escape(label)}</div>"
        f"<div class='secondary-value'>{escape(value)}</div>"
        "</div>"
    )


def _release_stage(key: str, value: str, note: str) -> str:
    return (
        "<div class='release-stage'>"
        f"<div class='release-stage-key'>{escape(key)}</div>"
        f"<div class='release-stage-value'>{escape(value)}</div>"
        f"<div class='release-stage-note'>{escape(note)}</div>"
        "</div>"
    )


def render_release_ruler(
    items: pd.DataFrame,
    latest_date: pd.Timestamp,
    *,
    headline: object,
    headline_delta: str | None,
    core_mm3m: object,
    diffusion_mm3m: object,
    regime_label: str,
) -> None:
    """The release in one scan: headline -> composition -> underlying -> breadth -> regime."""
    groups = items[(items["date"] == latest_date) & (items["level"] == "group")].dropna(
        subset=["contribution_mom"]
    )
    if groups.empty:
        composition_value, composition_note = "n/a", "composition unavailable"
    else:
        positive = groups.nlargest(1, "contribution_mom").iloc[0]
        negative = groups.nsmallest(1, "contribution_mom").iloc[0]
        composition_value = f"{positive['item_name']} {positive['contribution_mom']:+.2f} p.p."
        composition_note = (
            f"lowest: {negative['item_name']} {negative['contribution_mom']:+.2f} p.p."
        )
    _, delta_label = _delta_arrow(headline_delta)
    stages = [
        _release_stage("Headline", fmt(headline), delta_label or "unchanged vs. previous month"),
        _release_stage("Composition", composition_value, composition_note),
        _release_stage("Underlying", fmt(core_mm3m), "core mean · 3M average, NSA"),
        _release_stage("Diffusion", fmt(diffusion_mm3m), "share of price increases · 3M average"),
        _release_stage("Regime", regime_label, "deterministic classification"),
    ]
    st.markdown(
        f"<div class='release-ruler'>{''.join(stages)}</div>",
        unsafe_allow_html=True,
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

    st.title("OpenIPCA — Executive dashboard")
    st.caption(f"Latest processed data: {latest_date:%Y-%m} | Sources: BCB/SGS and IBGE/SIDRA")
    render_release_status(data)

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
    ipca_saar_sa = ipca.get("annualized_3m_sa") if ipca is not None else None
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
            "IPCA 3M average",
            "IPCA 3M average",
            fmt(ipca_mm3m),
            delta_pp(ipca_mm3m, ipca_prev["moving_average_3m"] if ipca_prev is not None else None),
        ),
    ]
    st.markdown(f"<div class='kpi-grid'>{''.join(tiles)}</div>", unsafe_allow_html=True)

    secondary = [
        _secondary_metric("IPCA 3M annualized SA", fmt(ipca_saar_sa)),
        _secondary_metric("Core inflation, 3M average", fmt(core_mm3m)),
        _secondary_metric("Diffusion 3M average", fmt(diff_mm3m)),
        _secondary_metric("Active alerts", str(len(alerts))),
    ]
    st.markdown(
        f"<div class='secondary-strip'>{''.join(secondary)}</div>",
        unsafe_allow_html=True,
    )

    regime = classify_latest_regime(bcb)
    render_release_ruler(
        items,
        latest_date,
        headline=ipca_mom,
        headline_delta=delta_pp(ipca_mom, ipca_prev["mom"] if ipca_prev is not None else None),
        core_mm3m=core_mm3m,
        diffusion_mm3m=diff_mm3m,
        regime_label=REGIME_LABELS.get(regime.label_pt, regime.label_pt),
    )
    st.markdown(
        "<div class='regime-row'><span class='regime-key'>Inflation regime:</span>"
        f"<span class='regime-pill'>{escape(REGIME_LABELS.get(regime.label_pt, regime.label_pt).upper())}</span></div>",
        unsafe_allow_html=True,
    )
    regime_explanation = describe(regime.label_pt)
    if regime_explanation:
        st.caption(regime_explanation)

    st.markdown(
        "<div class='diagnostic'><div class='callout-title info'>Monthly analysis</div>"
        f"{escape(english_diagnostic(data))}</div>",
        unsafe_allow_html=True,
    )

    render_top_movers(items, latest_date)

    with st.container(border=True):
        st.markdown(
            "<span class='ask-cta'></span>"
            "<div class='callout-title cta'>Ask the IPCA</div>"
            "Ask a question in English about inflation and get an answer "
            "grounded in official data, with every number traceable to evidence.",
            unsafe_allow_html=True,
        )
        if st.button("Open Ask the IPCA", key="open_ask"):
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

    st.plotly_chart(momentum_line(bcb), use_container_width=True)
    ipca_sa = (
        bcb.loc[bcb["series_short_name"] == "IPCA", "mom_sa"]
        if "mom_sa" in bcb.columns
        else None
    )
    if ipca_sa is not None and ipca_sa.notna().any():
        st.caption(
            "STL seasonal adjustment: the latest month's seasonal factor is an estimate and "
            "is revised as new data arrive. It is not an official IBGE/BCB figure."
        )

    render_active_alerts(alerts)


def render_item_search(items: pd.DataFrame, date: pd.Timestamp) -> None:
    """"How much did my item's price change?" — one-gesture answer for the question every
    visitor brings ("e o café? e a gasolina?").

    A searchable selectbox over the month's subitems -> mini-card with the
    month/12m variation, basket weight and a 24-month sparkline. The 3-level
    drilldown below stays for structure exploration; this is the shortcut.
    """
    options = subitem_options(items, date)
    if options.empty:
        return
    st.subheader("How much did my item's price change?")
    st.caption(
        f"Search among {len(options)} basket subitems, "
        "e.g. gasoline, rice or rent."
    )
    labels = dict(zip(options["classification_code"], options["item_name"], strict=False))
    codes = list(options["classification_code"].astype(str))
    requested_item = str(st.session_state.pop("nav_item", ""))
    if requested_item in codes:
        st.session_state["item_search"] = requested_item
    elif st.session_state.get("item_search") not in {None, *codes}:
        st.session_state.pop("item_search", None)
    chosen = st.selectbox(
        "Subitem",
        codes,
        index=None,
        format_func=lambda code: labels.get(code, code),
        placeholder="E.g. gasoline, coffee, rent…",
        key="item_search",
        label_visibility="collapsed",
    )
    if not chosen:
        return
    _set_query_params(
        view="decomposicao",
        month=date.strftime("%Y-%m"),
        item=str(chosen),
    )
    row = items[(items["classification_code"] == chosen) & (items["date"] == date)].iloc[0]
    name = str(row.get("item_name", chosen))
    col_mom, col_yoy, col_weight = st.columns(3)
    col_mom.metric(f"{name} — this month", fmt(row.get("mom")))
    col_yoy.metric("Over 12 months", fmt(row.get("yoy")))
    col_weight.metric("Basket weight", fmt(row.get("weight")))
    st.plotly_chart(subitem_sparkline(items, chosen), use_container_width=True)


def render_drilldown(items: pd.DataFrame, date: pd.Timestamp) -> None:
    """Navigate the hierarchy: group → subgroup → item → subitem.

    Answers 'which subitems make up an item?' using the parent/child links
    already in the data. Each step shows the children ordered by contribution.
    """
    st.subheader("Composition: from group to subitem")
    st.caption(
        "Choose a group and drill down to see its components. "
        "IPCA is organized as group → subgroup → item → subitem."
    )

    groups = top_level_rows(items, date)
    if groups.empty:
        st.info("No composition data for the selected month.")
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
            st.caption(f"{current['item_name']} has no subdivisions at this level.")
        else:
            label = node_label(items, current["classification_code"], date)
            st.markdown(
                f"{label} (price change {current['mom']:.2f}%, "
                f"contribution {current['contribution_mom']:.2f} p.p.) comprises:"
            )
            show = kids[["item_name", "mom", "contribution_mom", "weight"]].rename(
                columns={
                    "item_name": "Component",
                    "mom": "Price change (%)",
                    "contribution_mom": "Contribution (p.p.)",
                    "weight": "Weight (%)",
                }
            )
            st.dataframe(show, use_container_width=True, hide_index=True)


def page_decomposition(data: dict[str, pd.DataFrame]) -> None:
    items = data["items"]
    st.header("IPCA decomposition")
    st.caption(
        "**Price change (%)** is the monthly change in a group's prices, as reported by "
        "IBGE/SIDRA. **Contribution (p.p.)** is its impact on monthly IPCA "
        "= price change × weight ÷ 100. An item can have a large price change but a small contribution if "
        "its basket weight is small."
    )
    dates = [
        pd.Timestamp(value)
        for value in sorted(pd.to_datetime(items["date"]).dropna().unique())
    ]
    requested_month = str(st.session_state.pop("nav_month", ""))
    requested_date = (
        pd.Period(requested_month, freq="M").to_timestamp() if requested_month else None
    )
    selected_index = len(dates) - 1
    if requested_date in dates:
        selected_index = dates.index(requested_date)
        st.session_state.pop("decomp_month", None)
    elif st.session_state.get("decomp_month") not in dates:
        st.session_state.pop("decomp_month", None)
    selected_date = st.selectbox(
        "Reference month",
        dates,
        index=selected_index,
        format_func=lambda x: pd.Timestamp(x).strftime("%Y-%m"),
        key="decomp_month",
    )
    selected_date = pd.Timestamp(selected_date)
    _set_query_params(view="decomposicao", month=selected_date.strftime("%Y-%m"))
    level = st.selectbox(
        "Detail level (ranking and download)",
        ["group", "subgroup", "item", "subitem"],
        index=3,
        format_func=lambda lv: LEVEL_LABEL_PT.get(lv, lv),
    )

    # Time-series charts (always last 24 months — independent of the month picker).
    st.plotly_chart(stacked_contribution(items), use_container_width=True)
    left, right = st.columns(2)
    with left:
        st.caption(f"Waterfall and ranking refer to {selected_date:%Y-%m}.")
        st.plotly_chart(waterfall_latest(items, selected_date), use_container_width=True)
    with right:
        st.caption("Largest increases and decreases at the selected detail level.")
        st.plotly_chart(contribution_ranking(items, selected_date, level), use_container_width=True)
    st.plotly_chart(heatmap_groups(items), use_container_width=True)

    render_item_search(items, selected_date)
    render_drilldown(items, selected_date)

    latest = items[(items["date"] == selected_date) & (items["level"] == level)].copy()
    st.download_button(
        f"Download data ({LEVEL_LABEL_PT.get(level, level)}) — CSV",
        latest.sort_values("contribution_mom", ascending=False).to_csv(index=False).encode("utf-8"),
        file_name=f"ranking_{level}_{selected_date:%Y_%m}.csv",
        mime="text/csv",
    )


def page_cores(data: dict[str, pd.DataFrame]) -> None:
    cores = data["cores"]
    core_sets = load_yaml("core_sets.yaml").get("core_sets", {})
    labels = {key: value.get("label", key) for key, value in core_sets.items()}
    selected = st.selectbox(
        "Core set", list(labels), format_func=lambda key: translate_text(labels[key])
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
                    f"Incomplete set in the latest month: {avail}/{exp} series available. "
                    f"Missing: {missing}. The mean is omitted when the set is incomplete."
                )

    st.header("Core inflation monitor")
    # What "núcleos" are, then a legend for the cores in the selected conjunto.
    st.caption(describe("nucleos"))
    members = core_sets.get(selected, {}).get("members", [])
    if members:
        legend = "  \n".join(f"- {describe(m)}" for m in members if describe(m))
        if legend:
            with st.popover("What each core measure means"):
                st.markdown(legend)

    # Metric selector reuses the single-source METRIC_LABELS (same labels the
    # chart titles use, so they never diverge). Default to MM3M.
    # SA options only when the column exists in the processed data (older parquet,
    # or a build without statsmodels, simply won't offer them — no KeyError).
    metric_options = [
        m
        for m in (
            "moving_average_3m",
            "annualized_3m_sa",
            "mom_sa",
            "rolling_12m",
            "mom",
            "three_month_saar",
        )
        if m in cores.columns
    ]
    metric = st.selectbox(
        "Metric",
        metric_options,
        index=0,
        format_func=lambda key: METRIC_LABELS.get(key, key),
    )
    st.caption(
        "Seasonal adjustment (SA) uses STL: the latest seasonal factor is an estimate and "
        "is revised as data arrive. NSA means not seasonally adjusted. Neither is an "
        "official IBGE/BCB figure."
    )
    st.plotly_chart(core_lines(cores, selected, metric), use_container_width=True)
    st.plotly_chart(core_fan(cores, selected, metric), use_container_width=True)

    # Numeric detail behind a toggle: clean headers, useful columns only.
    with st.expander("View core measures in detail", expanded=False):
        st.caption("Latest values for each core measure in the selected set.")
        latest = (
            cores[cores["core_set_name"] == selected]
            .sort_values("date")
            .groupby("core_name")
            .tail(1)
            .sort_values("moving_average_3m", ascending=False)
        )
        rename = {
            "core_name": "Core",
            "mom": "Monthly (%)",
            "moving_average_3m": "3M average (%)",
            "rolling_12m": "12m (%)",
        }
        cols = [c for c in rename if c in latest.columns]
        st.dataframe(
            latest[cols].replace({"core_name": {"Media": "Average", "Média": "Average"}}).rename(columns=rename),
            use_container_width=True,
            hide_index=True,
        )


def page_diffusion(data: dict[str, pd.DataFrame]) -> None:
    bcb, items = data["bcb"], data["items"]
    st.header("Diffusion monitor")
    st.plotly_chart(diffusion_line(bcb), use_container_width=True)
    st.plotly_chart(ipca_diffusion_scatter(bcb), use_container_width=True)

    diffusion_by_group = calculate_diffusion_from_items(
        items, level="subitem", group_col="group_classification_code"
    )
    latest = diffusion_by_group[diffusion_by_group["date"] == diffusion_by_group["date"].max()]
    st.subheader("Calculated diffusion by group — latest month")
    st.dataframe(latest.rename(columns={"date": "Date", "group_classification_code": "Group code", "diffusion": "Diffusion (%)"}), use_container_width=True)


def page_alerts(data: dict[str, pd.DataFrame]) -> None:
    alerts = data["alerts"]
    st.header("Alerts")
    if alerts.empty:
        st.info("No active alerts in the latest run.")
    else:
        st.dataframe(alerts, use_container_width=True)
        st.download_button(
            "Download alerts CSV",
            alerts.to_csv(index=False).encode("utf-8"),
            file_name="alerts.csv",
            mime="text/csv",
        )


def page_methodology(data: dict[str, pd.DataFrame]) -> None:
    st.header("Methodology")
    st.markdown(METHODOLOGY_EN)
    validation_path = OUTPUTS_DIR / "validation_report.csv"
    if validation_path.exists():
        st.subheader("Validation report")
        validation = pd.read_csv(validation_path)
        st.dataframe(validation, use_container_width=True)
    st.subheader("Downloads")
    for name, frame in data.items():
        st.download_button(
            f"Download {name}.csv",
            frame.to_csv(index=False).encode("utf-8"),
            file_name=f"{name}.csv",
            mime="text/csv",
        )


# (css class, short uppercase label, explanation) for the answer's mode seal —
# a sober mono pill with a colored dot instead of an emoji.
_ASK_SEAL = {
    "ai": ("live", "LIVE", "Live answer grounded in official data."),
    "replay": ("", "PRE-GENERATED", "Pre-generated, audited answer (live AI is currently unavailable)."),
    "fallback": ("", "NO EVIDENCE", "There was insufficient evidence for a reliable answer."),
    "deterministic": (
        "live",
        "DATA",
        "Direct answer calculated from current data, without an external AI service.",
    ),
    "refused": (
        "refused",
        "OUT OF SCOPE",
        "Outside the inflation/IPCA scope or rejected by input checks.",
    ),
}


def render_evidence_navigation(rows: list[dict[str, object]]) -> None:
    """Render safe actions from resolved Q&A evidence into the relevant chart view."""
    targets: list[tuple[str, str, NavigationTarget]] = []
    seen: set[str] = set()
    for row in rows:
        evidence_id = str(row.get("evidence_id", ""))
        if not evidence_id or evidence_id in seen:
            continue
        target = target_for_evidence(evidence_id, row.get("date", ""))
        if target is None:
            continue
        seen.add(evidence_id)
        targets.append((evidence_id, str(row.get("metric", evidence_id)), target))
    if not targets:
        return
    st.markdown("**Open evidence in the dashboard:**")
    columns = st.columns(min(3, len(targets)))
    for index, (evidence_id, metric, target) in enumerate(targets):
        if columns[index % len(columns)].button(
            f"View: {metric}",
            key=f"open_evidence_{index}_{evidence_id}",
            use_container_width=True,
        ):
            _navigate_to_target(target)


def page_ask(data: dict[str, pd.DataFrame]) -> None:
    bcb, items, cores, alerts = data["bcb"], data["items"], data["cores"], data["alerts"]
    st.title("Ask the IPCA")
    st.caption(
        "Ask in English about Brazilian inflation. The answer is grounded in "
        "processed official data, with each number linked to evidence. With an "
        "AI key configured, answers can be generated live. Otherwise, the app "
        "uses current evidence directly. It "
        "never provides investment recommendations "
        "or Copom/Selic forecasts."
    )

    st.markdown("**Questions to get started:**")
    cols = st.columns(2)
    for index, question in enumerate(CURATED_QUESTIONS):
        if cols[index % 2].button(question, key=f"ask_sugg_{index}", use_container_width=True):
            st.session_state["qa_last_q"] = question

    typed = st.text_input(
        "Or type your question:",
        key="qa_input",
        placeholder="E.g. What drove inflation this month?",
    )
    if st.button("Ask", key="qa_submit", type="primary") and typed.strip():
        st.session_state["qa_last_q"] = typed.strip()

    question = st.session_state.get("qa_last_q")
    if not question:
        st.info("Choose a question above or type your own to get started.")
        return

    # Cache the answer for the current question and data month: Streamlit reruns on every widget
    # interaction, and without this each rerun would re-hit the live model — wasted
    # quota on a public box with no rate-limit. Only call when the question changes.
    try:
        data_month = pd.to_datetime(bcb["date"], errors="coerce").max().strftime("%Y-%m")
    except (KeyError, TypeError, ValueError):
        data_month = ""
    cache = st.session_state.get("qa_cache")
    if cache is None or cache.get("q") != question or cache.get("month") != data_month:
        with st.spinner("Consulting the IPCA data..."):
            result = answer_question(question, bcb, items, cores, alerts, language="en")
        st.session_state["qa_cache"] = {"q": question, "month": data_month, "result": result}
    result = st.session_state["qa_cache"]["result"]

    st.markdown(f"**You asked:** {question}")
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
        with st.expander("Evidence — every number linked to official data", expanded=False):
            # Resolved table (metric/value/source), not raw evidence_ids: the id
            # alone is unreadable; the promise is auditable BY HUMANS.
            rows = resolve_claim_evidence(result.claims, result.evidence)
            if rows:
                st.dataframe(
                    pd.DataFrame(rows).rename(
                        columns={
                            "claim": "Claim",
                            "evidence_id": "Evidence",
                            "metric": "Metric",
                            "value": "Value",
                            "unit": "Unit",
                            "date": "Date",
                            "source": "Source",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
                render_evidence_navigation(rows)


_PT_MONTHS = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}


def _status_strip_right(data: dict[str, pd.DataFrame]) -> str:
    """Freshness + quality seal for the strip: 'DATA ABR/2026 · 8/8 CHECKS OK'.

    Answers the first question any data-dashboard visitor has ("isso é de
    quando?") and surfaces the validation rigor that already runs every month.
    Only our own derived values go in (months/counts) — no user input.
    """
    parts: list[str] = []
    try:
        latest = pd.to_datetime(data["bcb"]["date"]).max()
        if pd.notna(latest):
            parts.append(f"DATA {_PT_MONTHS[latest.month]}/{latest.year}")
    except (KeyError, TypeError, ValueError):
        pass  # the strip must never break the app
    summary = summarize_report(OUTPUTS_DIR / "validation_report.csv")
    if summary:
        seal_cls = {"pass": "seal-ok", "warn": "seal-warn", "block": "seal-block"}[
            str(summary["worst"])
        ]
        label = f"{summary['passed']}/{summary['total']} CHECKS"
        if summary["worst"] == "pass":
            label += " OK"
        parts.append(f"<span class='{seal_cls}'>{label}</span>")
    state = read_release_state(RELEASE_STATE_PATH)
    runtime_status = release_freshness_status(state)
    if runtime_status == "due_today":
        parts.append("<span class='seal-warn'>RELEASE EXPECTED TODAY</span>")
    elif runtime_status == "overdue":
        parts.append("<span class='seal-warn'>DATA MAY BE OUT OF DATE</span>")
    return " · ".join(parts) or "openipca.streamlit.app"


@st.cache_data(show_spinner=False)
def _cached_build_stamp() -> str:
    # Cached so we don't shell out to git on every rerun; the cache clears on app
    # restart, so a new deploy refreshes the stamp.
    return build_stamp()


def main() -> None:
    try:
        data = load_data(processed_signature())
    except FileNotFoundError as exc:
        st.title("OpenIPCA")
        st.error("Processed data not found.")
        st.code("python -m ipca_dashboard.pipeline run\nstreamlit run dashboard/app.py")
        st.caption(str(exc))
        return

    raw_data = data
    data = display_data(data)
    _apply_query_params_once()

    pending = st.session_state.pop("pending_navigation", None)
    if isinstance(pending, dict) and pending.get("view") in PAGE_SLUGS:
        st.session_state["nav_page"] = PAGE_SLUGS[str(pending["view"])]
        if pending.get("month"):
            st.session_state["nav_month"] = str(pending["month"])
        if pending.get("item"):
            st.session_state["nav_item"] = str(pending["item"])

    # "Abrir Pergunte ao IPCA" (a button on the panel) routes here: promote its flag to
    # the nav radio's value BEFORE the radio is instantiated, so it renders pre-selected.
    if st.session_state.pop("goto_ask", False):
        st.session_state["nav_page"] = "Ask the IPCA"
        _set_query_params(view="pergunte", month="", evidence="", item="")

    st.sidebar.markdown(
        "<div class='brand'><span class='brand-mark'>I</span>"
        "<span class='brand-name'>Open<span class='brand-accent'>IPCA</span></span></div>"
        "<div class='nav-label'>Navigation</div>",
        unsafe_allow_html=True,
    )
    page = st.sidebar.radio(
        "Navigation",
        list(PAGE_SLUGS.values()),
        key="nav_page",
        label_visibility="collapsed",
    )
    _set_query_params(view=SLUG_BY_PAGE[page])
    st.sidebar.link_button(
        "Monthly reports",
        "https://github.com/Brunosavastano/OpenIPCA/releases",
        use_container_width=True,
    )
    # Glanceable "what's deployed" marker (short commit + date) — also the quickest
    # way to confirm an auto-deploy landed: it changes the moment a new commit is live.
    stamp = _cached_build_stamp()
    if stamp:
        st.sidebar.caption(f"build {stamp}")
    st.markdown(
        "<div class='status-strip'>"
        f"<span class='strip-left'><span class='dot'></span>{escape(page.upper())}</span>"
        f"<span class='strip-right'>{_status_strip_right(data)}</span></div>",
        unsafe_allow_html=True,
    )
    if page == "Executive dashboard":
        page_executive(data)
    elif page == "Ask the IPCA":
        page_ask(raw_data)
    elif page == "Decomposition":
        page_decomposition(data)
    elif page == "Core inflation":
        page_cores(data)
    elif page == "Diffusion":
        page_diffusion(data)
    elif page == "Alerts":
        page_alerts(data)
    else:
        page_methodology(data)


if __name__ == "__main__":
    main()
