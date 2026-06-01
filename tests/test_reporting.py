"""CP8 report tests — pure Markdown rendering, no network, no kaleido.

The PNG path is best-effort and not tested here (optional [report] dep); these
cover the deterministic, shareable Markdown core.
"""

import pandas as pd

import ipca_dashboard.reporting.build_report as build_report_module
from ipca_dashboard.reporting.render_markdown import (
    DISCLAIMER,
    render_report_markdown,
)


def _bcb() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {
                "date": date,
                "series_short_name": "IPCA",
                "mom": 0.30,
                "rolling_12m": 4.50,
                "moving_average_3m": 0.40,
            },
            {"date": date, "series_short_name": "Difusao", "mom": 58.0, "moving_average_3m": 55.0},
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


def test_build_report_default_does_not_import_static_chart_renderer(tmp_path, monkeypatch):
    import sys

    sys.modules.pop("ipca_dashboard.reporting.render_static_charts", None)

    def fake_load(name: str) -> pd.DataFrame:
        if name == "bcb_series_monthly.parquet":
            return _bcb()
        return pd.DataFrame()

    monkeypatch.setattr(build_report_module, "_load", fake_load)
    monkeypatch.setattr(build_report_module, "build_diagnostic_text", lambda *_args: _diagnostic())
    monkeypatch.setattr(build_report_module, "load_ai_brief", lambda _out_dir: None)

    result = build_report_module.build_report(tmp_path, with_charts=False)

    assert result["report"].exists()
    assert "ipca_dashboard.reporting.render_static_charts" not in sys.modules


def test_static_chart_timeout_is_bounded(tmp_path, monkeypatch):
    import subprocess

    import ipca_dashboard.reporting.render_static_charts as static_charts

    class FakeFig:
        def to_json(self) -> str:
            return "{}"

    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(static_charts.subprocess, "run", fake_run)

    result = static_charts._write_png(FakeFig(), tmp_path / "chart.png")

    assert result is None
