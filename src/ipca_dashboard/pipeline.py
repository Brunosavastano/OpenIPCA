from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

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
from ipca_dashboard.release import (
    build_release_state,
    load_release_state,
    next_release_date,
    utc_now,
)
from ipca_dashboard.transforms import build_core_metrics, transform_bcb_series, transform_ipca_items
from ipca_dashboard.validation import has_blocking_errors, validate_all

LOGGER = logging.getLogger(__name__)


class BlockingValidationError(RuntimeError):
    """Raised in strict mode when validation has blocking findings."""


class IncompleteSourceDataError(RuntimeError):
    """Raised when a source response cannot represent a complete reference month."""


RAW_BCB = RAW_DIR / "bcb_sgs.parquet"
RAW_SIDRA = RAW_DIR / "sidra_7060.parquet"
PROCESSED_BCB = PROCESSED_DIR / "bcb_series_monthly.parquet"
PROCESSED_ITEMS = PROCESSED_DIR / "ipca_items_monthly.parquet"
PROCESSED_CORES = PROCESSED_DIR / "core_metrics_monthly.parquet"
PROCESSED_ALERTS = PROCESSED_DIR / "alerts.parquet"
VALIDATION_REPORT = OUTPUTS_DIR / "validation_report.csv"
DIAGNOSTIC_JSON = OUTPUTS_DIR / "diagnostic_latest.json"
RELEASE_STATE_JSON = OUTPUTS_DIR / "release_state.json"

# Processed parquet filenames, written to staging then atomically promoted.
PROCESSED_FILENAMES = {
    "bcb": "bcb_series_monthly.parquet",
    "items": "ipca_items_monthly.parquet",
    "cores": "core_metrics_monthly.parquet",
    "alerts": "alerts.parquet",
}
# Separate fetch starts: the expanding percentiles (spec §4.6) need the LONG SGS
# history — a short window silently biases percentile_since_2012 and the public
# regime badge. SIDRA table 7060 simply does not exist before 2020. The monthly
# workflow runs `pipeline run --strict` with no flags, so these defaults are the
# single source of truth for what the public data contains.
DEFAULT_SGS_START = "2012-01"
DEFAULT_SIDRA_START = "2020-01"
# sgs_history_depth is the tripwire: if the SGS API ever caps the request window
# (it does not today — tested empirically), the strict cron fails closed BEFORE
# promoting short-history data. See spec §5.2 P1 (chunking only if ever needed).
STRICT_REQUIRED_PASS_CHECKS = {"critical_series_freshness", "sgs_history_depth"}
INCREMENTAL_BCB_OVERLAP_MONTHS = 24

_BCB_RAW_COLUMNS = [
    "date",
    "value",
    "series_group",
    "series_short_name",
    "series_name",
    "sgs_code",
    "unit",
    "source",
    "fetched_at",
]
_NORMALIZED_ITEM_COLUMNS = [
    "date",
    "source",
    "item_code",
    "classification_code",
    "item_name",
    "level",
    "parent_classification_code",
    "group_classification_code",
    "mom",
    "weight",
    "ytd",
    "yoy",
]


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


def _has_strict_rejection(validation_report) -> bool:
    if has_blocking_errors(validation_report):
        return True
    strict_checks = validation_report[validation_report["check"].isin(STRICT_REQUIRED_PASS_CHECKS)]
    return bool((strict_checks["status"] != "pass").any())


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _month_timestamp(value: str) -> pd.Timestamp:
    try:
        return pd.Period(value, freq="M").to_timestamp()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected month in YYYY-MM format, got {value!r}") from exc


def _validate_sidra_target_payload(
    raw: pd.DataFrame, config: dict[str, Any], expected_month: str
) -> None:
    """Reject partial table-7060 responses before they can enter the merge."""
    required_columns = {"D2C", "D3C", "D4C", "V"}
    if raw.empty or not required_columns.issubset(raw.columns):
        raise IncompleteSourceDataError("SIDRA target payload is empty or malformed.")
    expected_period = expected_month.replace("-", "")
    periods = set(raw["D3C"].astype(str))
    if periods != {expected_period}:
        raise IncompleteSourceDataError(
            f"SIDRA payload periods {sorted(periods)!r} do not match {expected_period}."
        )
    expected_variables = {
        str(meta["code"]) for meta in config.get("variables", {}).values() if "code" in meta
    }
    actual_variables = set(raw["D2C"].astype(str))
    if not expected_variables or actual_variables != expected_variables:
        raise IncompleteSourceDataError(
            f"SIDRA variables {sorted(actual_variables)!r} do not match "
            f"configured {sorted(expected_variables)!r}."
        )
    classifications = {
        variable: set(group["D4C"].astype(str))
        for variable, group in raw.groupby(raw["D2C"].astype(str))
    }
    first = next(iter(classifications.values()), set())
    if not first or any(codes != first for codes in classifications.values()):
        raise IncompleteSourceDataError(
            "SIDRA variables returned different classification sets for the target month."
        )
    if raw.duplicated(["D2C", "D3C", "D4C"]).any():
        raise IncompleteSourceDataError("SIDRA target payload contains duplicate variable rows.")
    numeric_values = pd.to_numeric(
        raw["V"].astype(str).str.replace(",", ".", regex=False), errors="coerce"
    )
    if numeric_values.isna().any():
        raise IncompleteSourceDataError("SIDRA target payload contains missing metric values.")


def _processed_bcb_as_raw(processed: pd.DataFrame) -> pd.DataFrame:
    if processed.empty:
        return pd.DataFrame(columns=_BCB_RAW_COLUMNS)
    raw = processed.copy().rename(columns={"mom": "value"})
    raw["fetched_at"] = ""
    for column in _BCB_RAW_COLUMNS:
        if column not in raw.columns:
            raw[column] = pd.NA
    return raw[_BCB_RAW_COLUMNS]


def _processed_items_as_normalized(processed: pd.DataFrame) -> pd.DataFrame:
    if processed.empty:
        return pd.DataFrame(columns=_NORMALIZED_ITEM_COLUMNS)
    normalized = processed.copy()
    for column in _NORMALIZED_ITEM_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    return normalized[_NORMALIZED_ITEM_COLUMNS]


def _replace_by_key(
    existing: pd.DataFrame, fresh: pd.DataFrame, keys: list[str]
) -> pd.DataFrame:
    """Prefer fresh rows by key while preserving untouched history."""
    if existing.empty:
        return fresh.drop_duplicates(keys, keep="last").reset_index(drop=True)
    if fresh.empty:
        return existing.drop_duplicates(keys, keep="last").reset_index(drop=True)
    combined = pd.concat([existing, fresh], ignore_index=True, sort=False)
    return combined.drop_duplicates(keys, keep="last").reset_index(drop=True)


def _release_state_payload(
    reference_month: str, context: dict[str, str] | None = None
) -> dict[str, object]:
    context = context or {}
    previous = load_release_state(RELEASE_STATE_JSON)
    same_release = previous.get("reference_month") == reference_month

    def previous_value(key: str) -> str:
        return str(previous.get(key, "")) if same_release else ""

    return build_release_state(
        reference_month,
        official_period_id=context.get("official_period_id", ""),
        source_modified_at=context.get(
            "source_modified_at", previous_value("source_modified_at")
        ),
        detected_at=context.get("detected_at", previous_value("detected_at")),
        built_at=context.get("built_at", previous_value("built_at") or utc_now()),
        next_release=context.get(
            "next_release_date", previous_value("next_release_date")
        ),
    )


def fetch_command(start_sgs: str | None, start_sidra: str | None, end: str | None) -> None:
    ensure_project_dirs()
    series_config = load_yaml("series_sgs.yaml")
    sidra_config = load_yaml("sidra_7060.yaml")
    bcb = fetch_all_sgs(series_config, start=start_sgs, end=end)
    sidra_raw = fetch_sidra_7060(sidra_config, start=start_sidra, end=end)
    write_parquet(bcb, RAW_BCB)
    write_parquet(sidra_raw, RAW_SIDRA)
    LOGGER.info("Wrote raw BCB data to %s", RAW_BCB)
    LOGGER.info("Wrote raw SIDRA data to %s", RAW_SIDRA)


def _build_from_inputs(
    raw_bcb: pd.DataFrame,
    sidra_items: pd.DataFrame,
    *,
    strict: bool = False,
    expected_month: str | None = None,
    release_context: dict[str, str] | None = None,
) -> None:
    core_sets_config = load_yaml("core_sets.yaml")
    alert_rules_config = load_yaml("alert_rules.yaml")

    # 1. Transform in memory.
    bcb = transform_bcb_series(raw_bcb)
    ipca_items = transform_ipca_items(sidra_items)
    core_metrics = build_core_metrics(bcb, core_sets_config)
    alerts = generate_alerts(alert_rules_config, bcb, core_metrics)

    # 2. Validate. The report is always written as an audit trail, even on abort.
    validation_report = validate_all(
        bcb, ipca_items, core_sets_config, expected_month=expected_month
    )
    write_csv(validation_report, VALIDATION_REPORT)
    blocking = has_blocking_errors(validation_report)
    strict_rejection = _has_strict_rejection(validation_report)

    # 3. In strict mode, abort BEFORE touching data/processed/ so good data stays.
    if strict_rejection and strict:
        LOGGER.error(
            "Strict build rejected: validation findings. "
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
    _write_json_atomic(DIAGNOSTIC_JSON, diagnostic)
    reference_month = str(diagnostic.get("reference_month", ""))
    if reference_month:
        completed_context = dict(release_context or {})
        if release_context is not None:
            completed_context["built_at"] = utc_now()
        _write_json_atomic(
            RELEASE_STATE_JSON,
            _release_state_payload(reference_month, completed_context),
        )

    if blocking:
        LOGGER.warning(
            "Build promoted WITH blocking validation findings (non-strict). See %s",
            VALIDATION_REPORT,
        )
    else:
        LOGGER.info("Build completed with no blocking validation findings.")


def build_command(
    strict: bool = False,
    *,
    expected_month: str | None = None,
    release_context: dict[str, str] | None = None,
) -> None:
    ensure_project_dirs()
    sidra_config = load_yaml("sidra_7060.yaml")
    raw_bcb = read_parquet(RAW_BCB)
    raw_sidra = read_parquet(RAW_SIDRA)
    sidra_items = normalize_sidra_7060(raw_sidra, sidra_config)
    _build_from_inputs(
        raw_bcb,
        sidra_items,
        strict=strict,
        expected_month=expected_month,
        release_context=release_context,
    )


def run_command(
    start_sgs: str | None,
    start_sidra: str | None,
    end: str | None,
    strict: bool = False,
    *,
    expected_month: str | None = None,
    release_context: dict[str, str] | None = None,
) -> None:
    fetch_command(start_sgs=start_sgs, start_sidra=start_sidra, end=end)
    build_command(
        strict=strict,
        expected_month=expected_month,
        release_context=release_context,
    )


def refresh_latest_command(
    expected_month: str,
    *,
    strict: bool = False,
    force_full: bool = False,
    detected_at: str = "",
    source_modified_at: str = "",
) -> str:
    """Refresh one newly detected month, falling back to the full rebuild when needed."""
    ensure_project_dirs()
    target = _month_timestamp(expected_month)
    required_processed = [PROCESSED_BCB, PROCESSED_ITEMS, PROCESSED_CORES, PROCESSED_ALERTS]
    have_base = all(path.exists() for path in required_processed)
    existing_bcb = read_parquet(PROCESSED_BCB) if have_base else pd.DataFrame()
    existing_items = read_parquet(PROCESSED_ITEMS) if have_base else pd.DataFrame()
    local_latest = (
        pd.to_datetime(existing_bcb["date"], errors="coerce").max()
        if not existing_bcb.empty and "date" in existing_bcb.columns
        else pd.NaT
    )
    if pd.notna(local_latest):
        local_latest = pd.Timestamp(local_latest).to_period("M").to_timestamp()
        if local_latest >= target and not force_full:
            LOGGER.info(
                "Processed data already covers %s; incremental refresh is a no-op.",
                expected_month,
            )
            return "current"

    release_context = {
        "official_period_id": expected_month.replace("-", ""),
        "source_modified_at": source_modified_at,
        "detected_at": detected_at or utc_now(),
        "next_release_date": next_release_date(expected_month),
    }
    month_gap = (
        target.to_period("M").ordinal - local_latest.to_period("M").ordinal
        if pd.notna(local_latest)
        else None
    )
    if force_full or not have_base or month_gap != 1:
        LOGGER.info(
            "Using full rebuild for %s (force=%s, base=%s, gap=%s).",
            expected_month,
            force_full,
            have_base,
            month_gap,
        )
        run_command(
            start_sgs=DEFAULT_SGS_START,
            start_sidra=DEFAULT_SIDRA_START,
            end=expected_month,
            strict=strict,
            expected_month=expected_month,
            release_context=release_context,
        )
        return "full"

    series_config = load_yaml("series_sgs.yaml")
    sidra_config = load_yaml("sidra_7060.yaml")
    overlap_start = (target.to_period("M") - (INCREMENTAL_BCB_OVERLAP_MONTHS - 1)).strftime(
        "%Y-%m"
    )
    fresh_bcb = fetch_all_sgs(series_config, start=overlap_start, end=expected_month)
    fresh_sidra_raw = fetch_sidra_7060(
        sidra_config, start=expected_month, end=expected_month
    )
    _validate_sidra_target_payload(fresh_sidra_raw, sidra_config, expected_month)
    fresh_items = normalize_sidra_7060(fresh_sidra_raw, sidra_config)

    merged_bcb = _replace_by_key(
        _processed_bcb_as_raw(existing_bcb),
        fresh_bcb,
        ["series_short_name", "date"],
    )
    merged_items = _replace_by_key(
        _processed_items_as_normalized(existing_items),
        fresh_items,
        ["date", "classification_code"],
    )
    _build_from_inputs(
        merged_bcb,
        merged_items,
        strict=strict,
        expected_month=expected_month,
        release_context=release_context,
    )
    return "incremental"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPCA dashboard data pipeline.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_fetch_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--start-sgs",
            default=DEFAULT_SGS_START,
            help="Start month (YYYY-MM) for BCB/SGS — percentiles need the long history.",
        )
        p.add_argument(
            "--start-sidra",
            default=DEFAULT_SIDRA_START,
            help="Start month (YYYY-MM) for IBGE/SIDRA 7060 (table only exists from 2020).",
        )
        p.add_argument("--end", default=None, help="End month in YYYY-MM format.")

    fetch = sub.add_parser("fetch", help="Fetch raw data from BCB/SGS and IBGE/SIDRA.")
    _add_fetch_args(fetch)

    build = sub.add_parser("build", help="Build processed datasets from raw parquet files.")
    build.add_argument(
        "--strict",
        action="store_true",
        help="Abort without promoting if validation has blocking findings.",
    )

    run = sub.add_parser("run", help="Fetch and build in one step.")
    _add_fetch_args(run)
    run.add_argument(
        "--strict",
        action="store_true",
        help="Abort without promoting if validation has blocking findings.",
    )

    refresh = sub.add_parser(
        "refresh-latest",
        help="Incrementally fetch a newly detected reference month.",
    )
    refresh.add_argument(
        "--expected-month",
        required=True,
        help="Official month detected by the lightweight probe (YYYY-MM).",
    )
    refresh.add_argument(
        "--strict",
        action="store_true",
        help="Abort without promoting unless the expected month is complete.",
    )
    refresh.add_argument(
        "--force-full",
        action="store_true",
        help="Force the long-history rebuild instead of the incremental path.",
    )
    refresh.add_argument("--detected-at", default="", help=argparse.SUPPRESS)
    refresh.add_argument("--source-modified-at", default="", help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(levelname)s:%(message)s",
    )
    if args.command == "fetch":
        fetch_command(start_sgs=args.start_sgs, start_sidra=args.start_sidra, end=args.end)
    elif args.command == "build":
        build_command(strict=args.strict)
    elif args.command == "run":
        run_command(
            start_sgs=args.start_sgs,
            start_sidra=args.start_sidra,
            end=args.end,
            strict=args.strict,
        )
    elif args.command == "refresh-latest":
        mode = refresh_latest_command(
            args.expected_month,
            strict=args.strict,
            force_full=args.force_full,
            detected_at=args.detected_at,
            source_modified_at=args.source_modified_at,
        )
        LOGGER.info("Refresh mode: %s", mode)
    else:  # pragma: no cover - argparse enforces commands.
        raise ValueError(args.command)


if __name__ == "__main__":
    main()
