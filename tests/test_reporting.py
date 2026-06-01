"""CP8 report tests — pure Markdown rendering, no network, no kaleido.

The PNG path is best-effort and not tested here (optional [report] dep); these
cover the deterministic, shareable Markdown core.
"""

import pandas as pd

from ipca_dashboard.reporting.render_markdown import (
    DISCLAIMER,
    render_report_markdown,
)


def _bcb() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {"date": date, "series_short_name": "IPCA", "mom": 0.30, "rolling_12m": 4.50,
             "moving_average_3m": 0.40},
            {"date": date, "series_short_name": "Difusao", "mom": 58.0,
             "moving_average_3m": 55.0},
        ]
    )


def _diagnostic() -> dict:
    return {
        "reference_month": "2024-03",
        "diagnostic": "O IPCA de 2024-03 veio em 0.30%...",
        "regime": "broad_disinflation",
        "regime_label": "Desinflação disseminada",
    }


def test_report_has_headline_numbers_and_regime():
    md = render_report_markdown(_bcb(), _diagnostic())
    assert "IPCA m/m:** 0.30%" in md
    assert "IPCA 12m:** 4.50%" in md
    assert "MM3M (NSA):** 0.40%" in md
    assert "Desinflação disseminada" in md


def test_report_includes_disclaimer_and_sources():
    md = render_report_markdown(_bcb(), _diagnostic())
    assert DISCLAIMER in md
    assert "IBGE/SIDRA" in md and "BCB/SGS" in md


def test_report_folds_in_ai_brief_when_present():
    md = render_report_markdown(_bcb(), _diagnostic(), ai_brief_md="## Brief\n- algo")
    assert "AI Replay Mode" in md
    assert "## Brief" in md


def test_report_omits_ai_section_when_absent():
    md = render_report_markdown(_bcb(), _diagnostic(), ai_brief_md=None)
    assert "AI Replay Mode" not in md


def test_report_embeds_charts_when_provided():
    md = render_report_markdown(_bcb(), _diagnostic(), charts=["charts/01_decomposition.png"])
    assert "![chart](charts/01_decomposition.png)" in md


def test_report_handles_missing_regime_gracefully():
    diag = {"reference_month": "2024-03", "diagnostic": "x"}  # no regime_label
    md = render_report_markdown(_bcb(), diag)
    assert "OpenIPCA — leitura do IPCA 2024-03" in md  # does not raise
