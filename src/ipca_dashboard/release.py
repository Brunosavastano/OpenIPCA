"""Official IPCA release detection and persisted release metadata.

This module intentionally uses only the Python standard library. The GitHub
Actions probe can therefore decide whether a refresh is needed before installing
the dashboard's data-science dependencies.
"""

from __future__ import annotations

import gzip
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PERIODS_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/7060/periodos"
# Latest headline row of the same table 7060, read from IBGE's SIDRA API, which is
# also where the refresh downloads the data. Since October 2026 the servicodados
# host drops connections from GitHub-hosted runners, while apisidra (behind a CDN)
# stays reachable, so the probe asks SIDRA first and servicodados second.
SIDRA_LATEST_URL = "https://apisidra.ibge.gov.br/values/t/7060/n1/all/v/63/p/last%201/c315/7169"
CALENDAR_URL = (
    "https://servicodados.ibge.gov.br/api/v3/calendario/"
    "indice-nacional-de-precos-ao-consumidor-amplo"
)
SIDRA_TABLE_URL = "https://apisidra.ibge.gov.br/values/t/7060"
BCB_SOURCE_URL = "https://www.bcb.gov.br/estatisticas/indecoreestruturais"
# Copy of the official calendar used when CALENDAR_URL cannot be reached (it lives
# on the same blocked host). Refresh it with scripts/update_ipca_calendar.py from a
# network that reaches IBGE once IBGE publishes the next year's dates.
CALENDAR_SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "ipca_release_calendar.json"
)
# Days a release may run late before an unreachable source fails the probe.
OVERDUE_GRACE_DAYS = 2
# Last day of the probe's usual release window (cron days 7-17).
_USUAL_LAST_RELEASE_DAY = 17
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_PERIOD_RE = re.compile(r"^\d{6}$")
_NUMBER_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")


class ReleaseProbeError(RuntimeError):
    """Raised when the official source cannot be read or trusted."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _request_json(
    url: str,
    *,
    timeout: float = 8.0,
    attempts: int = 3,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> object:
    """Read JSON with bounded retries; malformed data is never a false release."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = Request(url, headers={"User-Agent": "OpenIPCA/release-probe"})
            with opener(request, timeout=timeout) as response:
                raw = response.read()
                encoding = str(getattr(response, "headers", {}).get("Content-Encoding", ""))
            if encoding.lower() == "gzip" or raw.startswith(b"\x1f\x8b"):
                raw = gzip.decompress(raw)
            return json.loads(raw.decode("utf-8-sig"))
        except Exception as exc:  # noqa: BLE001 - source failures share one fail-closed path
            last_error = exc
            if attempt < attempts:
                sleeper(0.5 * attempt)
    detail = f" ({last_error!r})" if last_error is not None else ""
    raise ReleaseProbeError(f"Could not read trusted JSON from {url}{detail}") from last_error


def _iso_date(value: object) -> str:
    try:
        return datetime.strptime(str(value), "%d/%m/%Y").date().isoformat()
    except (TypeError, ValueError):
        return ""


def parse_latest_period(payload: object) -> dict[str, str]:
    """Return the latest valid monthly period from the Aggregates API payload."""
    if not isinstance(payload, list):
        raise ReleaseProbeError("IBGE periods payload is not a list.")
    valid = [
        item
        for item in payload
        if isinstance(item, dict) and _PERIOD_RE.fullmatch(str(item.get("id", "")))
    ]
    if not valid:
        raise ReleaseProbeError("IBGE periods payload has no valid monthly period.")
    latest = max(valid, key=lambda item: str(item["id"]))
    period_id = str(latest["id"])
    return {
        "official_period_id": period_id,
        "official_reference_month": f"{period_id[:4]}-{period_id[4:]}",
        "source_modified_at": _iso_date(latest.get("modificacao")),
    }


def parse_sidra_latest_period(payload: object) -> dict[str, str]:
    """Return the latest published month from SIDRA's table 7060 headline rows."""
    if not isinstance(payload, list) or len(payload) < 2:
        raise ReleaseProbeError("SIDRA payload has no data rows.")
    periods = [
        str(row["D3C"])
        for row in payload[1:]  # row 0 is SIDRA's column-label header
        if isinstance(row, dict)
        and _PERIOD_RE.fullmatch(str(row.get("D3C", "")))
        and str(row.get("D2C")) == "63"  # IPCA - monthly change
        and str(row.get("D4C")) == "7169"  # headline index
        and _NUMBER_RE.fullmatch(str(row.get("V", "")).strip())
    ]
    if not periods:
        raise ReleaseProbeError("SIDRA payload has no published headline month.")
    period_id = max(periods)
    return {
        "official_period_id": period_id,
        "official_reference_month": f"{period_id[:4]}-{period_id[4:]}",
        "source_modified_at": "",
    }


# Official sources of the latest month, tried in order; see SIDRA_LATEST_URL.
PERIOD_SOURCES: tuple[tuple[str, Callable[[object], dict[str, str]]], ...] = (
    (SIDRA_LATEST_URL, parse_sidra_latest_period),
    (PERIODS_URL, parse_latest_period),
)


def fetch_official_period(
    fetch_json: Callable[[str], object] = _request_json,
) -> dict[str, str]:
    """Latest official month from the first IBGE source that returns valid data."""
    errors: list[str] = []
    for url, parse in PERIOD_SOURCES:
        try:
            return {**parse(fetch_json(url)), "source_url": url}
        except ReleaseProbeError as exc:
            errors.append(str(exc))
    raise ReleaseProbeError("No official IBGE source answered: " + " | ".join(errors))


def load_local_reference_month(path: Path) -> str:
    """Best-effort reference month read; missing/malformed state means no local month."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = str(payload.get("reference_month", "")) if isinstance(payload, dict) else ""
    except (OSError, ValueError):
        return ""
    return value if _MONTH_RE.fullmatch(value) else ""


def month_distance(older: str, newer: str) -> int | None:
    if not (_MONTH_RE.fullmatch(older) and _MONTH_RE.fullmatch(newer)):
        return None
    old_year, old_month = (int(part) for part in older.split("-"))
    new_year, new_month = (int(part) for part in newer.split("-"))
    return (new_year - old_year) * 12 + new_month - old_month


def probe_release(
    diagnostic_path: Path,
    *,
    fetch_json: Callable[[str], object] = _request_json,
    detected_at: str | None = None,
) -> dict[str, object]:
    """Compare the official latest period with the committed local reference month."""
    official = fetch_official_period(fetch_json)
    local_month = load_local_reference_month(diagnostic_path)
    official_month = official["official_reference_month"]
    distance = month_distance(local_month, official_month)
    is_new = not local_month or (distance is not None and distance > 0)
    return {
        "status": "new" if is_new else "current",
        "local_reference_month": local_month,
        **official,
        "detected_at": detected_at or utc_now(),
        "requires_full_rebuild": not local_month or distance is None or distance > 1,
    }


def _shift_month(month: str, months: int) -> tuple[int, int]:
    year, number = (int(part) for part in month.split("-"))
    index = year * 12 + number - 1 + months
    return index // 12, index % 12 + 1


def release_deadline(state: dict[str, object], local_month: str) -> date | None:
    """Day the release after ``local_month`` is due, per the stored calendar date.

    Without a calendar date for that month, the end of the usual window (day 17 of
    the second month after it) stands in. ``None`` means there is no local month.
    """
    if not _MONTH_RE.fullmatch(local_month):
        return None
    if isinstance(state, dict) and state.get("reference_month") == local_month:
        try:
            return date.fromisoformat(str(state.get("next_release_date", "")))
        except ValueError:
            pass
    year, month = _shift_month(local_month, 2)
    return date(year, month, _USUAL_LAST_RELEASE_DAY)


def outage_is_actionable(
    state: dict[str, object],
    local_month: str,
    *,
    today: date | None = None,
    grace_days: int = OVERDUE_GRACE_DAYS,
) -> bool:
    """Whether an unreachable IBGE should fail the probe instead of only warning.

    While the published month is still the latest one due, an outage changes nothing
    for readers. It needs someone once the next release is ``grace_days`` late,
    because the dashboard is then going stale, or when there is no local month.
    """
    deadline = release_deadline(state, local_month)
    if deadline is None:
        return True
    return (today or _today_in_brazil()) > deadline + timedelta(days=grace_days)


def load_calendar_snapshot(path: Path = CALENDAR_SNAPSHOT_PATH) -> object:
    """Committed copy of the official calendar; empty when missing or malformed."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def next_release_date(
    reference_month: str,
    *,
    fetch_json: Callable[[str], object] = _request_json,
    snapshot_path: Path = CALENDAR_SNAPSHOT_PATH,
) -> str:
    """Best-effort next scheduled release date for a later reference month.

    Reads the live calendar and falls back to the committed snapshot when the live
    calendar is unreachable or has no usable date.
    """
    if not _MONTH_RE.fullmatch(reference_month):
        return ""
    try:
        live = _next_release_from_calendar(fetch_json(CALENDAR_URL), reference_month)
    except ReleaseProbeError:
        live = ""
    return live or _next_release_from_calendar(
        load_calendar_snapshot(snapshot_path), reference_month
    )


def _next_release_from_calendar(payload: object, reference_month: str) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        return ""
    candidates: list[tuple[str, date]] = []
    for item in payload["items"]:
        if not isinstance(item, dict):
            continue
        try:
            year = int(item["ano_referencia_inicio"])
            month_number = int(item["mes_referencia_inicio"])
            month = f"{year:04d}-{month_number:02d}"
            release_date = datetime.strptime(
                str(item["data_divulgacao"]), "%d/%m/%Y %H:%M:%S"
            ).date()
        except (KeyError, TypeError, ValueError):
            continue
        if month > reference_month:
            candidates.append((month, release_date))
    if not candidates:
        return ""
    _, release_date = min(candidates, key=lambda pair: (pair[0], pair[1]))
    return release_date.isoformat()


def build_release_state(
    reference_month: str,
    *,
    official_period_id: str = "",
    source_modified_at: str = "",
    detected_at: str = "",
    built_at: str = "",
    next_release: str = "",
) -> dict[str, object]:
    """Create the versioned, fixed-time release metadata consumed by the app."""
    if not _MONTH_RE.fullmatch(reference_month):
        raise ValueError(f"Invalid reference month: {reference_month!r}")
    return {
        "schema_version": 1,
        "reference_month": reference_month,
        "official_period_id": official_period_id or reference_month.replace("-", ""),
        "source_modified_at": source_modified_at,
        "detected_at": detected_at,
        "built_at": built_at or utc_now(),
        "next_release_date": next_release,
        "source_urls": {
            "periods": PERIODS_URL,
            "calendar": CALENDAR_URL,
            "sidra": SIDRA_TABLE_URL,
            "bcb": BCB_SOURCE_URL,
        },
    }


def load_release_state(path: Path) -> dict[str, object]:
    """Load release metadata without ever breaking the public app."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return {}
    month = str(payload.get("reference_month", ""))
    return payload if _MONTH_RE.fullmatch(month) else {}


def freshness_status(state: dict[str, object], *, today: date | None = None) -> str:
    """Classify runtime freshness from fixed metadata: current/due_today/overdue/unknown."""
    raw = str(state.get("next_release_date", "")) if isinstance(state, dict) else ""
    try:
        next_date = date.fromisoformat(raw)
    except ValueError:
        return "unknown"
    current = today if today is not None else _today_in_brazil()
    if current < next_date:
        return "current"
    if current == next_date:
        return "due_today"
    return "overdue"


def _today_in_brazil() -> date:
    try:
        return datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    except ZoneInfoNotFoundError:  # pragma: no cover - Linux/Cloud ships tzdata
        return datetime.now(UTC).date()
