from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import pandas as pd

from ipca_dashboard._http import session_with_retries

LOGGER = logging.getLogger(__name__)
SIDRA_BASE_URL = "https://apisidra.ibge.gov.br/values"


def _month_chunks(start: str | None, end: str | None, chunk_size: int = 12) -> list[str]:
    start = start or "2020-01"
    end = end or datetime.now(UTC).strftime("%Y-%m")
    periods = pd.period_range(start=start, end=end, freq="M")
    chunks: list[str] = []
    for idx in range(0, len(periods), chunk_size):
        chunk = periods[idx : idx + chunk_size]
        start_code = chunk[0].strftime("%Y%m")
        end_code = chunk[-1].strftime("%Y%m")
        chunks.append(start_code if start_code == end_code else f"{start_code}-{end_code}")
    return chunks


def _chunks(values: list[str], chunk_size: int) -> list[list[str]]:
    return [values[idx : idx + chunk_size] for idx in range(0, len(values), chunk_size)]


def _parse_classification_name(value: str) -> tuple[str, str]:
    if value == "Indice geral" or value == "Índice geral":
        return "", "Indice geral"
    match = re.match(r"^(\d+)\.(.*)$", value)
    if not match:
        return "", value
    return match.group(1), match.group(2).strip()


def _level_from_classification(code: str) -> str:
    length = len(code)
    if length == 0:
        return "headline"
    if length == 1:
        return "group"
    if length == 2:
        return "subgroup"
    if length == 4:
        return "item"
    if length >= 7:
        return "subitem"
    return "other"


def fetch_sidra_7060(
    config: dict[str, Any],
    start: str | None = None,
    end: str | None = None,
    timeout: int = 90,
) -> pd.DataFrame:
    table = int(config.get("table", 7060))
    territory = config.get("territory", {})
    classification = config.get("classification", {})
    variables = config.get("variables", {})

    variable_codes = [str(meta["code"]) for meta in variables.values()]
    period_chunks = _month_chunks(start, end)
    territory_level = int(territory.get("level", 1))
    territory_code = int(territory.get("code", 1))
    classification_code = int(classification.get("code", 315))

    session = session_with_retries()
    frames: list[pd.DataFrame] = []
    for period in period_chunks:
        for variable_chunk in _chunks(variable_codes, 2):
            variable_selector = ",".join(variable_chunk)
            url = (
                f"{SIDRA_BASE_URL}/t/{table}/n{territory_level}/{territory_code}"
                f"/v/{variable_selector}/p/{period}/c{classification_code}/all"
            )
            LOGGER.info("Fetching SIDRA table %s variables %s period %s", table, variable_selector, period)
            response = session.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "ipca-dashboard/0.1"},
            )
            response.raise_for_status()
            payload = response.json()
            if len(payload) > 1:
                frames.append(pd.DataFrame(payload[1:]))
    if not frames:
        return pd.DataFrame()
    raw = pd.concat(frames, ignore_index=True)
    raw["source"] = "IBGE/SIDRA"
    raw["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    return raw


def normalize_sidra_7060(raw: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()
    variable_map = {
        str(meta["code"]): metric_name for metric_name, meta in config.get("variables", {}).items()
    }
    df = raw.copy()
    df["date"] = pd.to_datetime(df["D3C"].astype(str), format="%Y%m", errors="coerce")
    df["metric"] = df["D2C"].astype(str).map(variable_map)
    df["value"] = pd.to_numeric(
        df["V"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    parsed = df["D4N"].astype(str).apply(_parse_classification_name)
    df["classification_code"] = parsed.apply(lambda item: item[0])
    df["item_name"] = parsed.apply(lambda item: item[1])
    df["level"] = df["classification_code"].apply(_level_from_classification)
    df["parent_classification_code"] = df["classification_code"].map(_parent_code)
    df["group_classification_code"] = df["classification_code"].str.slice(0, 1)

    index_cols = [
        "date",
        "source",
        "D4C",
        "classification_code",
        "item_name",
        "level",
        "parent_classification_code",
        "group_classification_code",
    ]
    wide = (
        df.dropna(subset=["date", "metric"])
        .pivot_table(index=index_cols, columns="metric", values="value", aggfunc="first")
        .reset_index()
        .rename(columns={"D4C": "item_code"})
    )
    for col in ["mom", "weight", "ytd", "yoy"]:
        if col not in wide.columns:
            wide[col] = pd.NA
    return wide.sort_values(["date", "level", "classification_code"]).reset_index(drop=True)


def _parent_code(code: str) -> str:
    if not code:
        return ""
    if len(code) == 1:
        return ""
    if len(code) == 2:
        return code[:1]
    if len(code) == 4:
        return code[:2]
    if len(code) >= 7:
        return code[:4]
    return code[:-1]
