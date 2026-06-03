"""Static safety checks for the data refresh automation."""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFRESH_WORKFLOW = ROOT / ".github" / "workflows" / "refresh-data.yml"

EXPECTED_VERSIONED_DATA = {
    "data/processed/alerts.parquet",
    "data/processed/bcb_series_monthly.parquet",
    "data/processed/core_metrics_monthly.parquet",
    "data/processed/ipca_items_monthly.parquet",
    "outputs/diagnostic_latest.json",
    "outputs/validation_report.csv",
}


def _workflow_text() -> str:
    return REFRESH_WORKFLOW.read_text(encoding="utf-8")


def test_refresh_workflow_has_no_push_trigger_and_uses_skip_ci():
    text = _workflow_text()
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "\n  push:" not in text
    assert "\npush:" not in text
    assert "[skip ci]" in text


def test_refresh_workflow_uses_minimal_write_permission_and_strict_pipeline():
    text = _workflow_text()
    assert "permissions:\n  contents: write" in text
    assert "python -m ipca_dashboard.pipeline run --strict" in text


def test_refresh_workflow_stages_only_app_data_artifacts():
    text = _workflow_text()
    assert (
        "git add data/processed/*.parquet outputs/validation_report.csv "
        "outputs/diagnostic_latest.json"
    ) in text
    assert "data/raw" not in text
    assert "processed_staging" not in text
    assert ".env" not in text


def test_only_expected_app_data_artifacts_are_tracked():
    tracked_result = subprocess.run(
        ["git", "ls-files", "data", "outputs"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    deleted_result = subprocess.run(
        ["git", "ls-files", "--deleted", "data", "outputs"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    tracked = {
        line.strip().replace("\\", "/")
        for line in tracked_result.stdout.splitlines()
        if line.strip()
    }
    deleted = {
        line.strip().replace("\\", "/")
        for line in deleted_result.stdout.splitlines()
        if line.strip()
    }
    tracked -= deleted
    assert tracked == EXPECTED_VERSIONED_DATA
