import math

import pandas as pd

from ipca_dashboard.transforms import (
    calc_3m_saar,
    expanding_percentile,
    percentile_midrank,
    transform_bcb_series,
    transform_ipca_items,
)


def test_three_month_saar_formula():
    series = pd.Series([1.0, 1.0, 1.0])
    result = calc_3m_saar(series).iloc[-1]
    expected = 100 * ((1.01**3) ** 4 - 1)
    assert math.isclose(result, expected, rel_tol=1e-10)


def test_ipca_contribution_formula_and_simple_12m():
    dates = pd.date_range("2024-01-01", periods=12, freq="MS")
    rows = []
    for date in dates:
        rows.append(
            {
                "date": date,
                "source": "test",
                "item_code": "headline",
                "classification_code": "",
                "item_name": "Indice geral",
                "level": "headline",
                "parent_classification_code": "",
                "group_classification_code": "",
                "weight": 100.0,
                "mom": 0.5,
                "ytd": None,
                "yoy": None,
                "fetched_at": "test",
            }
        )
        rows.append(
            {
                "date": date,
                "source": "test",
                "item_code": "g1",
                "classification_code": "1",
                "item_name": "Grupo 1",
                "level": "group",
                "parent_classification_code": "",
                "group_classification_code": "1",
                "weight": 40.0,
                "mom": 2.0,
                "ytd": None,
                "yoy": None,
                "fetched_at": "test",
            }
        )
    result = transform_ipca_items(pd.DataFrame(rows))
    group = result[result["classification_code"] == "1"].sort_values("date")
    assert group["contribution_mom"].iloc[0] == 0.8
    assert math.isclose(group["contribution_12m_simple"].iloc[-1], 9.6)
    assert "fetched_at" not in result.columns


def test_transform_bcb_series_drops_execution_timestamp_from_processed_output():
    raw = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=24, freq="MS"),
            "value": [0.5] * 24,
            "source": ["BCB/SGS"] * 24,
            "sgs_code": [433] * 24,
            "series_name": ["IPCA"] * 24,
            "series_short_name": ["IPCA"] * 24,
            "series_group": ["headline"] * 24,
            "unit": ["pct_mom"] * 24,
            "fetched_at": ["run-clock"] * 24,
        }
    )
    result = transform_bcb_series(raw)
    assert "fetched_at" not in result.columns
    changed_clock = raw.copy()
    changed_clock["fetched_at"] = "next-run-clock"
    pd.testing.assert_frame_equal(result, transform_bcb_series(changed_clock))


def test_transform_ipca_items_is_stable_when_only_fetch_timestamp_changes():
    dates = pd.date_range("2024-01-01", periods=12, freq="MS")
    rows = [
        {
            "date": date,
            "source": "IBGE/SIDRA",
            "item_code": "headline",
            "classification_code": "",
            "item_name": "Indice geral",
            "level": "headline",
            "parent_classification_code": "",
            "group_classification_code": "",
            "weight": 100.0,
            "mom": 0.5,
            "ytd": None,
            "yoy": None,
            "fetched_at": "first-run-clock",
        }
        for date in dates
    ]
    first = transform_ipca_items(pd.DataFrame(rows))
    rows_next = [{**row, "fetched_at": "next-run-clock"} for row in rows]
    second = transform_ipca_items(pd.DataFrame(rows_next))
    assert "fetched_at" not in first.columns
    pd.testing.assert_frame_equal(first, second)


def test_percentile_midrank_handles_ties():
    window = pd.Series([1.0, 1.0, 1.0, 1.0])
    # All equal: less=0, equal=4 -> 50.0, not an artificial p100.
    assert math.isclose(percentile_midrank(window, 1.0), 50.0, rel_tol=1e-10)


def test_percentile_midrank_basic_rank():
    window = pd.Series([1.0, 2.0, 3.0, 4.0])
    # current=3: less=2, equal=1 -> (2 + 0.5) / 4 * 100 = 62.5
    assert math.isclose(percentile_midrank(window, 3.0), 62.5, rel_tol=1e-10)


def test_percentile_midrank_ignores_nan_in_window():
    window = pd.Series([1.0, 2.0, float("nan"), 4.0])
    # valid = [1, 2, 4]; current=2: less=1, equal=1 -> (1 + 0.5) / 3 * 100 = 50.0
    assert math.isclose(percentile_midrank(window, 2.0), 50.0, rel_tol=1e-10)


def test_percentile_midrank_empty_window_returns_nan():
    assert math.isnan(percentile_midrank(pd.Series([], dtype=float), 1.0))


def test_expanding_percentile_constant_series_not_p100():
    series = pd.Series([5.0] * 30)
    out = expanding_percentile(series, min_periods=24)
    # Constant series -> mid-rank ~50, never 100.
    assert math.isclose(out.iloc[-1], 50.0, rel_tol=1e-10)

