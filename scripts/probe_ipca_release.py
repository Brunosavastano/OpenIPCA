"""Dependency-free IBGE release probe used before package installation in CI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ipca_dashboard.release import (  # noqa: E402
    OVERDUE_GRACE_DAYS,
    ReleaseProbeError,
    load_local_reference_month,
    load_release_state,
    outage_is_actionable,
    probe_release,
    release_deadline,
    utc_now,
)


def _write_github_outputs(result: dict[str, object]) -> None:
    path = os.getenv("GITHUB_OUTPUT")
    if not path:
        return
    values = {
        "status": result.get("status", ""),
        "official_month": result.get("official_reference_month", ""),
        "local_month": result.get("local_reference_month", ""),
        "requires_full_rebuild": str(bool(result.get("requires_full_rebuild"))).lower(),
        "source_modified_at": result.get("source_modified_at", ""),
        "detected_at": result.get("detected_at", ""),
    }
    with Path(path).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _write_step_summary(text: str) -> None:
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(text + "\n")


def _annotation(text: str) -> str:
    """Escape a GitHub Actions workflow-command message."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _unavailable(args: argparse.Namespace, error: ReleaseProbeError) -> tuple[dict, bool]:
    """Result for a run where no official source answered, and whether to fail it."""
    local_month = load_local_reference_month(Path(args.diagnostic))
    state = load_release_state(Path(args.release_state))
    deadline = release_deadline(state, local_month)
    result = {
        "status": "unavailable",
        "local_reference_month": local_month,
        "official_period_id": "",
        "official_reference_month": "",
        "source_modified_at": "",
        "source_url": "",
        "detected_at": utc_now(),
        "requires_full_rebuild": False,
        "next_release_due": deadline.isoformat() if deadline else "",
        "error": str(error),
    }
    return result, outage_is_actionable(state, local_month)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether IBGE table 7060 has a new month.")
    parser.add_argument(
        "--json", action="store_true", help="Print one machine-readable JSON object."
    )
    parser.add_argument(
        "--diagnostic",
        default=str(ROOT / "outputs" / "diagnostic_latest.json"),
        help="Committed diagnostic JSON used as the local reference month.",
    )
    parser.add_argument(
        "--release-state",
        default=str(ROOT / "outputs" / "release_state.json"),
        help="Committed release metadata holding the next official release date.",
    )
    args = parser.parse_args(argv)
    try:
        result = probe_release(Path(args.diagnostic))
    except ReleaseProbeError as exc:
        result, actionable = _unavailable(args, exc)
        local = result["local_reference_month"] or "none"
        due = result["next_release_due"] or "unknown"
        if actionable:
            message = (
                f"No official IBGE source answered and the release due {due} is more than "
                f"{OVERDUE_GRACE_DAYS} days late, so the published data ({local}) is going "
                "stale. Check the IBGE sources or run the refresh from a network that reaches "
                "them."
            )
            print(f"release probe failed: {message} {exc}", file=sys.stderr)
            _write_step_summary(f"**Release probe failed.** {message}\n\n`{exc}`")
            return 2
        message = (
            f"No official IBGE source answered. The published data ({local}) stays current "
            f"until the next release (due {due}), so this run only warns. {exc}"
        )
        print(f"::warning title=IBGE unreachable::{_annotation(message)}")
        _write_step_summary(f"**IBGE unreachable, nothing to do yet.** {message}")
    _write_github_outputs(result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(
            f"{result['status']}: local={result['local_reference_month'] or 'none'} "
            f"official={result['official_reference_month'] or 'unknown'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
