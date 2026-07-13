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

from ipca_dashboard.release import ReleaseProbeError, probe_release  # noqa: E402


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
    args = parser.parse_args(argv)
    try:
        result = probe_release(Path(args.diagnostic))
    except ReleaseProbeError as exc:
        print(f"release probe failed: {exc}", file=sys.stderr)
        return 2
    _write_github_outputs(result)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(
            f"{result['status']}: local={result['local_reference_month'] or 'none'} "
            f"official={result['official_reference_month']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
