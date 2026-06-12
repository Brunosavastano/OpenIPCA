"""The long-history tripwire: percentiles are only honest with the 2012+ window.

validate_sgs_history_depth feeds pipeline.STRICT_REQUIRED_PASS_CHECKS, so the
monthly strict build fails closed BEFORE promoting short-history data (e.g. a
--start-sgs regression or a future SGS API window cap).
"""

import logging

import pandas as pd

from ipca_dashboard.fetch_bcb import fetch_all_sgs
from ipca_dashboard.validation import (
    MIN_SGS_HISTORY_MONTHS,
    validate_all,
    validate_sgs_history_depth,
)


def _bcb(months: int) -> pd.DataFrame:
    dates = pd.date_range("2012-01-01", periods=months, freq="MS")
    return pd.DataFrame(
        {
            "date": list(dates) * 2,
            "series_short_name": ["IPCA"] * months + ["Difusao"] * months,
            "series_group": ["headline"] * months + ["diffusion"] * months,
            "mom": [0.4] * months + [60.0] * months,
        }
    )


def test_long_history_passes():
    report = validate_sgs_history_depth(_bcb(172))
    assert report.iloc[0]["status"] == "pass"
    assert report.iloc[0]["value"] == 172


def test_short_history_warns():
    report = validate_sgs_history_depth(_bcb(76))  # the old 2020+ window
    assert report.iloc[0]["status"] == "warn"
    assert report.iloc[0]["value"] == 76


def test_threshold_sits_between_old_and_new_windows():
    assert 76 < MIN_SGS_HISTORY_MONTHS < 172


def test_empty_dataset_warns_not_crashes():
    report = validate_sgs_history_depth(pd.DataFrame())
    assert report.iloc[0]["status"] == "warn"


def test_check_is_wired_into_validate_all():
    report = validate_all(_bcb(172), pd.DataFrame(), {})
    assert "sgs_history_depth" in set(report["check"])


def test_fetch_all_sgs_logs_truncation_warning(monkeypatch, caplog):
    """A series starting after the requested month must be surfaced loudly —
    it means a late series or an API window cap (chunking territory)."""
    config = {"series": {"headline": {"IPCA": {"code": 433, "label": "IPCA"}}}}
    short = pd.DataFrame(
        {"date": pd.date_range("2020-01-01", periods=3, freq="MS"), "value": [1.0, 2.0, 3.0]}
    )
    monkeypatch.setattr(
        "ipca_dashboard.fetch_bcb.fetch_sgs_series", lambda code, start=None, end=None: short
    )
    with caplog.at_level(logging.WARNING):
        fetch_all_sgs(config, start="2012-01")
    assert any("window cap" in record.message for record in caplog.records)


def test_fetch_all_sgs_no_warning_when_history_is_complete(monkeypatch, caplog):
    config = {"series": {"headline": {"IPCA": {"code": 433, "label": "IPCA"}}}}
    full = pd.DataFrame(
        {"date": pd.date_range("2012-01-01", periods=170, freq="MS"), "value": [1.0] * 170}
    )
    monkeypatch.setattr(
        "ipca_dashboard.fetch_bcb.fetch_sgs_series", lambda code, start=None, end=None: full
    )
    with caplog.at_level(logging.WARNING):
        fetch_all_sgs(config, start="2012-01")
    assert not any("window cap" in record.message for record in caplog.records)
