from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

from ipca_dashboard.alerts import generate_alerts
from ipca_dashboard.config import (
    OUTPUTS_DIR,
    PROCESSED_DIR,
    PROCESSED_STAGING_DIR,
    RAW_DIR,
    ensure_project_dirs,
    load_yaml,
)
from ipca_dashboard.diagnostics import build_diagnostic_text
from ipca_dashboard.fetch_bcb import fetch_all_sgs
from ipca_dashboard.fetch_ibge import fetch_sidra_7060, normalize_sidra_7060
from ipca_dashboard.io import read_parquet, write_csv, write_parquet
from ipca_dashboard.transforms import build_core_metrics, transform_bcb_series, transform_ipca_items
from ipca_dashboard.validation import has_blocking_errors, validate_all


LOGGER = logging.getLogger(__name__)


class BlockingValidationError(RuntimeError):
    """Raised in strict mode when validation has blocking findings."""


RAW_BCB = RAW_DIR / "bcb_sgs.parquet"
RAW_SIDRA = RAW_DIR / "sidra_7060.parquet"
PROCESSED_BCB = PROCESSED_DIR / "bcb_series_monthly.parquet"
PROCESSED_ITEMS = PROCESSED_DIR / "ipca_items_monthly.parquet"
PROCESSED_CORES = PROCESSED_DIR / "core_metrics_monthly.parquet"
PROCESSED_ALERTS = PROCESSED_DIR / "alerts.parquet"
VALIDATION_REPORT = OUTPUTS_DIR / "validation_report.csv"
DIAGNOSTIC_JSON = OUTPUTS_DIR / "diagnostic_latest.json"

# Processed parquet filenames, written to staging then atomically promoted.
PROCESSED_FILENAMES = {
    "bcb": "bcb_series_monthly.parquet",
    "items": "ipca_items_monthly.parquet",
    "cores": "core_metrics_monthly.parquet",
    "alerts": "alerts.parquet",
}


def _promote_staging_to_processed(filenames: dict[str, str]) -> None:
    """Move each staged parquet onto its processed path atomically (os.replace).

    os.replace is atomic per file on the same volume (staging and processed are
    both under data/), so a good processed file is never left half-written.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name in filenames.values():
        staged = PROCESSED_STAGING_DIR / name
        final = PROCESSED_DIR / name
        os.replace(staged, final)


def fetch_command(start: str | None, end: str | None) -> None:
    ensure_project_dirs()
    series_config = load_yaml("series_sgs.yaml")
    sidra_config = load_yaml("sidra_7060.yaml")
    bcb = fetch_all_sgs(series_config, start=start, end=end)
    sidra_raw = fetch_sidra_7060(sidra_config, start=start, end=end)
    write_parquet(bcb, RAW_BCB)
    write_parquet(sidra_raw, RAW_SIDRA)
    LOGGER.info("Wrote raw BCB data to %s", RAW_BCB)
    LOGGER.info("Wrote raw SIDRA data to %s", RAW_SIDRA)


def build_command(strict: bool = False) -> None:
    ensure_project_dirs()
    sidra_config = load_yaml("sidra_7060.yaml")
    core_sets_config = load_yaml("core_sets.yaml")
    alert_rules_config = load_yaml("alert_rules.yaml")

    raw_bcb = read_parquet(RAW_BCB)
    raw_sidra = read_parquet(RAW_SIDRA)

    # 1. Transform in memory.
    bcb = transform_bcb_series(raw_bcb)
    sidra_items = normalize_sidra_7060(raw_sidra, sidra_config)
    ipca_items = transform_ipca_items(sidra_items)
    core_metrics = build_core_metrics(bcb, core_sets_config)
    alerts = generate_alerts(alert_rules_config, bcb, core_metrics)

    # 2. Validate. The report is always written as an audit trail, even on abort.
    validation_report = validate_all(bcb, ipca_items, core_sets_config)
    write_csv(validation_report, VALIDATION_REPORT)
    blocking = has_blocking_errors(validation_report)

    # 3. In strict mode, abort BEFORE touching data/processed/ so good data stays.
    if blocking and strict:
        LOGGER.error(
            "Strict build rejected: blocking validation findings. "
            "data/processed/ left unchanged. See %s",
            VALIDATION_REPORT,
        )
        raise BlockingValidationError(
            "Blocking validation findings in strict mode; processed data not promoted."
        )

    # 4. Write to staging.
    PROCESSED_STAGING_DIR.mkdir(parents=True, exist_ok=True)
    write_parquet(bcb, PROCESSED_STAGING_DIR / PROCESSED_FILENAMES["bcb"])
    write_parquet(ipca_items, PROCESSED_STAGING_DIR / PROCESSED_FILENAMES["items"])
    write_parquet(core_metrics, PROCESSED_STAGING_DIR / PROCESSED_FILENAMES["cores"])
    write_parquet(alerts, PROCESSED_STAGING_DIR / PROCESSED_FILENAMES["alerts"])

    # 5. Promote staging -> processed atomically (per file).
    _promote_staging_to_processed(PROCESSED_FILENAMES)

    diagnostic = build_diagnostic_text(bcb, ipca_items, core_metrics, alerts)
    DIAGNOSTIC_JSON.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")

    if blocking:
        LOGGER.warning(
            "Build promoted WITH blocking validation findings (non-strict). See %s",
            VALIDATION_REPORT,
        )
    else:
        LOGGER.info("Build completed with no blocking validation findings.")


def run_command(start: str | None, end: str | None, strict: bool = False) -> None:
    fetch_command(start=start, end=end)
    build_command(strict=strict)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPCA dashboard data pipeline.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Fetch raw data from BCB/SGS and IBGE/SIDRA.")
    fetch.add_argument("--start", default="2020-01", help="Start month in YYYY-MM format.")
    fetch.add_argument("--end", default=None, help="End month in YYYY-MM format.")

    build = sub.add_parser("build", help="Build processed datasets from raw parquet files.")
    build.add_argument(
        "--strict",
        action="store_true",
        help="Abort without promoting if validation has blocking findings.",
    )

    run = sub.add_parser("run", help="Fetch and build in one step.")
    run.add_argument("--start", default="2020-01", help="Start month in YYYY-MM format.")
    run.add_argument("--end", default=None, help="End month in YYYY-MM format.")
    run.add_argument(
        "--strict",
        action="store_true",
        help="Abort without promoting if validation has blocking findings.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s:%(message)s")
    if args.command == "fetch":
        fetch_command(start=args.start, end=args.end)
    elif args.command == "build":
        build_command(strict=args.strict)
    elif args.command == "run":
        run_command(start=args.start, end=args.end, strict=args.strict)
    else:  # pragma: no cover - argparse enforces commands.
        raise ValueError(args.command)


if __name__ == "__main__":
    main()

