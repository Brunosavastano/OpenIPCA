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
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

PERIODS_URL = "https://servicodados.ibge.gov.br/api/v3/agregados/7060/periodos"
CALENDAR_URL = (
    "https://servicodados.ibge.gov.br/api/v3/calendario/"
    "indice-nacional-de-precos-ao-consumidor-amplo"
)
SIDRA_TABLE_URL = "https://apisidra.ibge.gov.br/values/t/7060"
BCB_SOURCE_URL = "https://www.bcb.gov.br/estatisticas/indecoreestruturais"
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_PERIOD_RE = re.compile(r"^\d{6}$")


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
    raise ReleaseProbeError(f"Could not read trusted JSON from {url}") from last_error


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
        if isinstance(item, dict)
        and _PERIOD_RE.fullmatch(str(item.get("id", "")))
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
    official = parse_latest_period(fetch_json(PERIODS_URL))
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
        "source_url": PERIODS_URL,
    }


def next_release_date(
    reference_month: str,
    *,
    fetch_json: Callable[[str], object] = _request_json,
) -> str:
    """Best-effort next scheduled release date for a later reference month."""
    if not _MONTH_RE.fullmatch(reference_month):
        return ""
    try:
        payload = fetch_json(CALENDAR_URL)
    except ReleaseProbeError:
        return ""
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
    if today is not None:
        current = today
    else:
        try:
            current = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        except ZoneInfoNotFoundError:  # pragma: no cover - Linux/Cloud ships tzdata
            current = datetime.now(UTC).date()
    if current < next_date:
        return "current"
    if current == next_date:
        return "due_today"
    return "overdue"
