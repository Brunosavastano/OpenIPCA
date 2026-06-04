"""Generate the AI brief artifacts from processed data (BYOK, run once).

This is the Phase-B entry point: with a provider configured via env
(OPENIPCA_AI_ENABLED / OPENIPCA_AI_PROVIDER) and a key present, it produces a
real grounded brief; with no key it cleanly falls back to the deterministic
brief. Either way it writes reports/latest/{ai_brief.md,ai_trace.json,metadata.json}.

Usage:
    python -m ipca_dashboard.ai.cli
The artifacts are committed (no key is ever written); the published app replays them.
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ipca_dashboard.ai.brief import generate_brief, write_brief_artifacts
from ipca_dashboard.ai.env import load_env_once
from ipca_dashboard.config import PROCESSED_DIR, PROJECT_ROOT

LOGGER = logging.getLogger(__name__)
REPORTS_LATEST = PROJECT_ROOT / "reports" / "latest"


def _load(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the grounded AI brief artifacts.")
    parser.add_argument("--out", default=str(REPORTS_LATEST), help="Output directory.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s:%(message)s")

    if load_env_once():
        LOGGER.info("Loaded configuration from .env")

    bcb = _load("bcb_series_monthly.parquet")
    items = _load("ipca_items_monthly.parquet")
    cores = _load("core_metrics_monthly.parquet")
    alerts = _load("alerts.parquet")
    if bcb.empty:
        raise SystemExit("No processed data found. Run the pipeline first.")

    reference_month = pd.to_datetime(bcb["date"]).max().strftime("%Y-%m")
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    result = generate_brief(bcb, items, cores, alerts, generated_at=generated_at)
    paths = write_brief_artifacts(result, Path(args.out), reference_month)

    if result.used_fallback:
        LOGGER.warning("Brief generated via deterministic fallback (%s).", result.error)
    else:
        LOGGER.info("Brief generated via provider '%s'.", result.provider_name)
    for label, path in paths.items():
        LOGGER.info("Wrote %s -> %s", label, path)


if __name__ == "__main__":
    main()
