"""Refresh config/ipca_release_calendar.json from IBGE's official release calendar.

The calendar API lives on servicodados.ibge.gov.br, which has dropped connections
from GitHub-hosted runners since October 2026. The refresh therefore falls back to
this committed copy for the next release date. Run this script from a network that
reaches IBGE (for example, a computer in Brazil) after IBGE publishes the next
year's calendar, usually in December, and commit the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ipca_dashboard.release import (  # noqa: E402
    CALENDAR_SNAPSHOT_PATH,
    CALENDAR_URL,
    ReleaseProbeError,
    _request_json,
    utc_now,
)

_FIELDS = ("ano_referencia_inicio", "mes_referencia_inicio", "data_divulgacao")


def build_snapshot(payload: object, retrieved_at: str) -> dict[str, object]:
    """Keep the fields next_release_date reads, from the year before retrieval on."""
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ReleaseProbeError("IBGE calendar payload has no items list.")
    first_year = int(retrieved_at[:4]) - 1
    items = []
    for item in payload["items"]:
        try:
            row = {field: item[field] for field in _FIELDS}
            year, month = int(row["ano_referencia_inicio"]), int(row["mes_referencia_inicio"])
        except (KeyError, TypeError, ValueError):
            continue
        if year >= first_year and 1 <= month <= 12:
            items.append(row)
    if not items:
        raise ReleaseProbeError("IBGE calendar payload has no usable release dates.")
    items.sort(
        key=lambda row: (int(row["ano_referencia_inicio"]), int(row["mes_referencia_inicio"]))
    )
    return {"source_url": CALENDAR_URL, "retrieved_at": retrieved_at, "items": items}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default=str(CALENDAR_SNAPSHOT_PATH))
    args = parser.parse_args(argv)
    try:
        snapshot = build_snapshot(_request_json(CALENDAR_URL), utc_now())
    except ReleaseProbeError as exc:
        print(f"calendar update failed: {exc}", file=sys.stderr)
        return 2
    output = Path(args.output)
    output.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    last = snapshot["items"][-1]
    print(
        f"wrote {len(snapshot['items'])} release dates to {output}; the last one covers "
        f"{int(last['ano_referencia_inicio']):04d}-{int(last['mes_referencia_inicio']):02d} "
        f"({last['data_divulgacao']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
