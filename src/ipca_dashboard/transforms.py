from __future__ import annotations

import numpy as np
import pandas as pd


MONTHLY_LIKE_GROUPS = {"headline", "aggregates", "cores", "underlying"}


def calc_3m_saar(series: pd.Series) -> pd.Series:
    gross = 1 + pd.to_numeric(series, errors="coerce") / 100
    return 100 * (gross.rolling(3, min_periods=3).apply(np.prod, raw=True) ** 4 - 1)


def calc_rolling_12m(series: pd.Series) -> pd.Series:
    gross = 1 + pd.to_numeric(series, errors="coerce") / 100
    return 100 * (gross.rolling(12, min_periods=12).apply(np.prod, raw=True) - 1)


def rolling_zscore(series: pd.Series, window: int = 60, min_periods: int = 24) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std()
    return (values - mean) / std.replace(0, np.nan)


def percentile_midrank(window: pd.Series, current: float) -> float:
    """Mid-rank percentile of ``current`` within ``window`` (handles ties).

    Uses ``(less + 0.5 * equal) / n`` so a constant or tie-heavy series scores
    ~50 instead of an artificial p100. NaNs are dropped from the window; returns
    NaN if the window is empty or ``current`` is NaN.
    """
    valid = pd.to_numeric(window, errors="coerce").dropna()
    if len(valid) == 0 or pd.isna(current):
        return float("nan")
    less = int((valid < current).sum())
    equal = int((valid == current).sum())
    return 100.0 * (less + 0.5 * equal) / len(valid)


def expanding_percentile(series: pd.Series, min_periods: int = 24) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    out = pd.Series(np.nan, index=values.index, dtype=float)
    for idx in range(len(values)):
        current = values.iloc[idx]
        window = values.iloc[: idx + 1].dropna()
        if len(window) < min_periods or pd.isna(current):
            continue
        out.iloc[idx] = percentile_midrank(window, current)
    return out


def calculate_diffusion_from_items(
    items: pd.DataFrame,
    level: str = "subitem",
    group_col: str | None = None,
) -> pd.DataFrame:
    """Share of items with positive m/m, excluding missing m/m from the denominator.

    Groups by ``date`` (and optionally ``group_col``). Returns a frame with
    columns ``date``, optionally ``group_col``, and ``diffusion`` (0-100).
    Dropping NaN m/m is the fix: a missing reading must not count as
    "not positive" and deflate diffusion.
    """
    valid = items[items["level"] == level].dropna(subset=["mom"]).copy()
    valid["positive"] = valid["mom"] > 0
    keys = ["date"] if group_col is None else ["date", group_col]
    out = valid.groupby(keys, as_index=False)["positive"].mean()
    out["diffusion"] = out["positive"] * 100.0
    return out.drop(columns="positive")


def transform_bcb_series(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw.copy()
    df = raw.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    df["mom"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.sort_values(["series_short_name", "date"]).reset_index(drop=True)

    transformed: list[pd.DataFrame] = []
    for _, group in df.groupby("series_short_name", sort=False):
        group = group.copy()
        is_monthly_rate = group["series_group"].iloc[0] in MONTHLY_LIKE_GROUPS
        if is_monthly_rate:
            group["rolling_12m"] = calc_rolling_12m(group["mom"])
            group["three_month_saar"] = calc_3m_saar(group["mom"])
        else:
            group["rolling_12m"] = np.nan
            group["three_month_saar"] = np.nan
        group["moving_average_3m"] = group["mom"].rolling(3, min_periods=3).mean()
        group["moving_average_6m"] = group["mom"].rolling(6, min_periods=6).mean()
        group["zscore_60m"] = rolling_zscore(group["mom"])
        group["percentile_since_2012"] = expanding_percentile(group["mom"])
        group["moving_average_3m_percentile"] = expanding_percentile(group["moving_average_3m"])
        transformed.append(group)
    columns = [
        "date",
        "source",
        "sgs_code",
        "series_name",
        "series_short_name",
        "series_group",
        "unit",
        "mom",
        "rolling_12m",
        "three_month_saar",
        "moving_average_3m",
        "moving_average_6m",
        "zscore_60m",
        "percentile_since_2012",
        "moving_average_3m_percentile",
    ]
    return pd.concat(transformed, ignore_index=True)[columns]


def build_core_metrics(bcb: pd.DataFrame, core_sets_config: dict) -> pd.DataFrame:
    core_sets = core_sets_config.get("core_sets", {})
    cores = bcb[bcb["series_group"] == "cores"].copy()
    if cores.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for set_name, metadata in core_sets.items():
        members = metadata.get("members", [])
        member_rows = cores[cores["series_short_name"].isin(members)].copy()
        if member_rows.empty:
            continue
        member_rows["core_set_name"] = set_name
        member_rows["core_set_label"] = metadata.get("label", set_name)
        member_rows["core_name"] = member_rows["series_short_name"]
        frames.append(
            member_rows[
                [
                    "date",
                    "core_set_name",
                    "core_set_label",
                    "core_name",
                    "mom",
                    "rolling_12m",
                    "three_month_saar",
                    "moving_average_3m",
                    "zscore_60m",
                    "percentile_since_2012",
                ]
            ]
        )

        pivot = member_rows.pivot_table(index="date", columns="series_short_name", values="mom")
        # Reindex to the full member list so a missing core becomes an all-NaN
        # column (no KeyError) and is visibly counted as missing.
        pivot = pivot.reindex(columns=members)
        expected_count = len(members)
        available_count = pivot.notna().sum(axis=1)
        is_complete = available_count == expected_count
        missing_members = pivot.apply(
            lambda row: ",".join(m for m in members if pd.isna(row[m])), axis=1
        )
        # skipna=False: the mean is only valid when every member is present;
        # otherwise it is NaN (default require_complete behaviour, spec §4.5).
        mean_mom = pivot.mean(axis=1, skipna=False)
        mean = pd.DataFrame(
            {
                "date": mean_mom.index,
                "mom": mean_mom.values,
                "n_members_expected": expected_count,
                "n_members_available": available_count.values,
                "is_complete": is_complete.values,
                "is_complete_core_set": is_complete.values,
                "missing_members": missing_members.values,
            }
        ).sort_values("date")
        mean["core_set_name"] = set_name
        mean["core_set_label"] = metadata.get("label", set_name)
        mean["core_name"] = "Média"
        mean["rolling_12m"] = calc_rolling_12m(mean["mom"])
        mean["three_month_saar"] = calc_3m_saar(mean["mom"])
        mean["moving_average_3m"] = mean["mom"].rolling(3, min_periods=3).mean()
        mean["zscore_60m"] = rolling_zscore(mean["mom"])
        mean["percentile_since_2012"] = expanding_percentile(mean["mom"])
        frames.append(
            mean[
                [
                    "date",
                    "core_set_name",
                    "core_set_label",
                    "core_name",
                    "mom",
                    "rolling_12m",
                    "three_month_saar",
                    "moving_average_3m",
                    "zscore_60m",
                    "percentile_since_2012",
                    "n_members_expected",
                    "n_members_available",
                    "is_complete",
                    "is_complete_core_set",
                    "missing_members",
                ]
            ]
        )
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(
        ["core_set_name", "core_name", "date"]
    )


def transform_ipca_items(items: pd.DataFrame) -> pd.DataFrame:
    if items.empty:
        return items.copy()
    df = items.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.to_period("M").dt.to_timestamp()
    for col in ["mom", "weight", "ytd", "yoy"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["contribution_mom"] = df["weight"] * df["mom"] / 100
    df = df.sort_values(["classification_code", "date"]).reset_index(drop=True)
    df["contribution_12m_simple"] = (
        df.groupby("classification_code")["contribution_mom"]
        .rolling(12, min_periods=12)
        .sum()
        .reset_index(level=0, drop=True)
    )
    chain = _chain_contribution(df)
    df = df.merge(chain, on=["date", "classification_code"], how="left")
    return df.drop(columns=["fetched_at"], errors="ignore")


def _chain_contribution(df: pd.DataFrame) -> pd.DataFrame:
    headline = (
        df[df["level"] == "headline"][["date", "mom"]]
        .drop_duplicates("date")
        .sort_values("date")
        .set_index("date")
    )
    if headline.empty:
        return pd.DataFrame(columns=["date", "classification_code", "contribution_12m_chain"])
    headline_index = (1 + headline["mom"] / 100).cumprod() * 100
    index_prev = headline_index.shift(1)
    if not index_prev.empty:
        index_prev.iloc[0] = 100.0

    matrix = df.pivot_table(
        index="date",
        columns="classification_code",
        values="contribution_mom",
        aggfunc="first",
    ).sort_index()
    common_dates = matrix.index.intersection(headline_index.index)
    matrix = matrix.loc[common_dates]
    index_prev = index_prev.loc[common_dates]
    headline_index = headline_index.loc[common_dates]

    rows: list[pd.DataFrame] = []
    for idx in range(12, len(common_dates)):
        target_date = common_dates[idx]
        base = headline_index.iloc[idx - 12]
        if pd.isna(base) or base == 0:
            continue
        window_dates = common_dates[idx - 11 : idx + 1]
        factors = index_prev.loc[window_dates] / base
        weighted = matrix.loc[window_dates].mul(factors, axis=0).sum(min_count=1)
        result = weighted.rename("contribution_12m_chain").reset_index()
        result["date"] = target_date
        rows.append(result)
    if not rows:
        return pd.DataFrame(columns=["date", "classification_code", "contribution_12m_chain"])
    out = pd.concat(rows, ignore_index=True).rename(columns={"index": "classification_code"})
    return out[["date", "classification_code", "contribution_12m_chain"]]


def top_movers(
    items: pd.DataFrame,
    date: pd.Timestamp,
    n: int = 5,
    min_weight: float = 0.1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Top-N subitems by 12m variation (yoy), up and down, for the month.

    The selection rule is PURE and declared (weight >= min_weight, ranked by the
    official yoy) — no hand-curated "everyday items" list, which would be an
    editorial choice disguised as a ranking. The weight floor keeps sub-0.1%
    curiosities (e.g. tiny produce) from crowding out items people actually buy.

    Returns (up, down) with item_name/yoy/mom/weight, both possibly empty —
    callers must omit the card rather than crash (e.g. yoy column absent).
    """
    required = {"date", "level", "item_name", "yoy", "mom", "weight"}
    if items.empty or not required.issubset(items.columns):
        empty = pd.DataFrame(columns=["item_name", "yoy", "mom", "weight"])
        return empty, empty
    rows = items[
        (items["date"] == date)
        & (items["level"] == "subitem")
        & (items["weight"].notna())
        & (items["weight"] >= min_weight)
        & (items["yoy"].notna())
    ][["item_name", "yoy", "mom", "weight"]]
    up = rows.nlargest(n, "yoy").reset_index(drop=True)
    down = rows.nsmallest(n, "yoy").sort_values("yoy").reset_index(drop=True)
    return up, down
