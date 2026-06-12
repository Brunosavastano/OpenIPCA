"""The status-strip quality seal: counts + worst status from validation_report.csv.

The seal must be able to DEGRADE — a badge that can never turn amber/red is a
vanity seal. And it must be omitted (None) when the report is missing, never
invented.
"""

from pathlib import Path

import pandas as pd

from ipca_dashboard.validation import summarize_report


def _write_report(path: Path, statuses: list[str]) -> Path:
    pd.DataFrame(
        {
            "check": [f"check_{i}" for i in range(len(statuses))],
            "status": statuses,
            "value": [0] * len(statuses),
            "details": ["d"] * len(statuses),
        }
    ).to_csv(path, index=False)
    return path


def test_all_pass(tmp_path: Path):
    summary = summarize_report(_write_report(tmp_path / "r.csv", ["pass"] * 8))
    assert summary == {"total": 8, "passed": 8, "worst": "pass"}


def test_warn_degrades_the_seal(tmp_path: Path):
    summary = summarize_report(_write_report(tmp_path / "r.csv", ["pass", "warn", "pass"]))
    assert summary == {"total": 3, "passed": 2, "worst": "warn"}


def test_block_outranks_warn(tmp_path: Path):
    summary = summarize_report(_write_report(tmp_path / "r.csv", ["warn", "block", "pass"]))
    assert summary is not None
    assert summary["worst"] == "block"
    assert summary["passed"] == 1


def test_missing_or_malformed_report_yields_none(tmp_path: Path):
    assert summarize_report(tmp_path / "nope.csv") is None
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    assert summarize_report(empty) is None
    no_status = tmp_path / "no_status.csv"
    pd.DataFrame({"check": ["a"], "value": [0]}).to_csv(no_status, index=False)
    assert summarize_report(no_status) is None


def test_against_the_real_committed_report():
    real = Path(__file__).resolve().parents[1] / "outputs" / "validation_report.csv"
    if not real.exists():  # CI checkout always has it, but stay robust
        return
    summary = summarize_report(real)
    assert summary is not None
    assert summary["total"] >= summary["passed"] >= 0
    assert summary["worst"] in ("pass", "warn", "block")
