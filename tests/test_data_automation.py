"""Static safety checks for release detection and publication automation."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
REFRESH_WORKFLOW = WORKFLOWS / "refresh-data.yml"
RECONCILE_WORKFLOW = WORKFLOWS / "reconcile-data.yml"
REPORT_WORKFLOW = WORKFLOWS / "publish-release-report.yml"
AI_WORKFLOW = WORKFLOWS / "refresh-ai-artifacts.yml"

EXPECTED_VERSIONED_DATA = {
    "data/processed/alerts.parquet",
    "data/processed/bcb_series_monthly.parquet",
    "data/processed/core_metrics_monthly.parquet",
    "data/processed/ipca_items_monthly.parquet",
    "outputs/diagnostic_latest.json",
    "outputs/release_state.json",
    "outputs/validation_report.csv",
}


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_refresh_probes_frequently_before_installing_dependencies():
    text = _text(REFRESH_WORKFLOW)
    assert 'cron: "2-57/5 11-22 7-17 * *"' in text
    assert "python scripts/probe_ipca_release.py --json" in text
    assert text.index("probe_ipca_release.py") < text.index('pip install -e ".[pipeline]"')
    assert "workflow_dispatch:" in text
    assert "cancel-in-progress: false" in text


def test_refresh_publishes_only_strict_deterministic_data():
    text = _text(REFRESH_WORKFLOW)
    assert "pipeline refresh-latest" in text
    assert "--expected-month" in text and "--strict" in text
    assert "outputs/release_state.json" in text
    assert "data/raw" not in text and "processed_staging" not in text
    assert "ipca_dashboard.ai" not in text
    assert "OPENAI_API_KEY" not in text
    assert "git push origin HEAD:main" in text
    assert "git push --force" not in text
    assert "[skip ci]" in text
    assert "steps.publish.outputs.changed == 'true'" in text
    assert "gh workflow run publish-release-report.yml" in text
    assert "gh workflow run refresh-ai-artifacts.yml" in text


def test_weekly_reconciliation_uses_full_strict_pipeline_and_shared_lock():
    refresh = _text(REFRESH_WORKFLOW)
    reconcile = _text(RECONCILE_WORKFLOW)
    assert 'cron: "27 10 * * 0"' in reconcile
    assert "python -m ipca_dashboard.pipeline run --strict" in reconcile
    assert "group: openipca-release-refresh" in refresh
    assert "group: openipca-release-refresh" in reconcile
    assert "git push --force" not in reconcile


def test_report_is_separate_best_effort_release_asset_workflow():
    text = _text(REPORT_WORKFLOW)
    assert "workflow_run:" not in text
    assert "workflow_dispatch:" in text
    assert "ipca_dashboard.reporting.build_report --latest --with-charts" in text
    assert 'tag="ipca-${month}"' in text
    assert "reports/latest/report.md" in text
    assert "reports/latest/report.png" in text
    assert "gh release upload" in text
    assert "OPENAI_API_KEY" not in text


def test_ai_artifacts_are_proposed_by_pr_not_committed_with_data():
    text = _text(AI_WORKFLOW)
    assert "workflow_run:" not in text
    assert "workflow_dispatch:" in text
    assert "ipca_dashboard.ai.cli" in text
    assert "ipca_dashboard.ai.qa_replay" in text
    assert "${{ secrets.OPENAI_API_KEY }}" in text
    assert "gh pr create --base main" in text
    assert "git push --set-upstream origin" in text
    assert "git push origin HEAD:main" not in text
    assert "AI replay is empty or stale" in text


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
    # Newly-added files do not appear in git ls-files until staged; include the
    # working-tree release state explicitly so this assertion remains useful pre-commit.
    if (ROOT / "outputs" / "release_state.json").exists():
        tracked.add("outputs/release_state.json")
    assert tracked == EXPECTED_VERSIONED_DATA
