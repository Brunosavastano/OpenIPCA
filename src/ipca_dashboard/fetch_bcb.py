from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)
BCB_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"


def flatten_series_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group, series in config.get("series", {}).items():
        if not isinstance(series, dict):
            continue
        for short_name, metadata in series.items():
            rows.append(
                {
                    "series_group": group,
                    "series_short_name": short_name,
                    "series_name": metadata.get("label", short_name),
                    "sgs_code": int(metadata["code"]),
                    "unit": metadata.get("unit", "pct_mom"),
                }
            )
    if not rows:
        raise ValueError("No SGS series configured.")
    return rows


def _month_to_bcb_date(month: str | None, *, end: bool = False) -> str | None:
    if month is None:
        return None
    year, month_num = month.split("-")
    if end:
        return f"28/{month_num}/{year}"
    return f"01/{month_num}/{year}"


def fetch_sgs_series(
    code: int,
    start: str | None = None,
    end: str | None = None,
    timeout: int = 30,
    retries: int = 3,
) -> pd.DataFrame:
    params = {"formato": "json"}
    start_date = _month_to_bcb_date(start)
    end_date = _month_to_bcb_date(end, end=True)
    if start_date:
        params["dataInicial"] = start_date
    if end_date:
        params["dataFinal"] = end_date

    url = BCB_BASE_URL.format(code=code)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=timeout,
                headers={"User-Agent": "ipca-dashboard/0.1"},
            )
            response.raise_for_status()
            payload = response.json()
            if not payload:
                return pd.DataFrame(columns=["date", "value"])
            df = pd.DataFrame(payload)
            df["date"] = pd.to_datetime(df["data"], dayfirst=True, errors="coerce")
            df["date"] = df["date"].dt.to_period("M").dt.to_timestamp()
            df["value"] = pd.to_numeric(
                df["valor"].astype(str).str.replace(",", ".", regex=False),
                errors="coerce",
            )
            return df[["date", "value"]].dropna(subset=["date"])
        except Exception as exc:  # pragma: no cover - retry path depends on network.
            last_error = exc
            LOGGER.warning("SGS %s failed on attempt %s/%s: %s", code, attempt, retries, exc)
            time.sleep(1.5 * attempt)
    raise RuntimeError(f"Could not fetch SGS series {code}") from last_error


def fetch_all_sgs(
    config: dict[str, Any],
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    frames: list[pd.DataFrame] = []
    for metadata in flatten_series_config(config):
        LOGGER.info("Fetching SGS %s (%s)", metadata["sgs_code"], metadata["series_name"])
        df = fetch_sgs_series(metadata["sgs_code"], start=start, end=end)
        for key, value in metadata.items():
            df[key] = value
        df["source"] = "BCB/SGS"
        df["fetched_at"] = fetched_at
        frames.append(df)
    if not frames:
        raise ValueError("No SGS data fetched.")
    return pd.concat(frames, ignore_index=True).sort_values(["series_short_name", "date"])
