"""Seasonal adjustment (STL) — transforms-level contract.

The adversarial core: SA actually removes a known seasonal pattern; it is
deterministic; and it is fail-soft — a short series, an interior gap, or a missing
statsmodels (the build-time `pipeline` extra) all degrade to an all-NaN series
instead of crashing the pipeline. The numeric SA columns flow through
``transform_bcb_series`` and ``build_core_metrics``.
"""

import numpy as np
import pandas as pd
import pytest

from ipca_dashboard import transforms
from ipca_dashboard.transforms import (
    build_core_metrics,
    seasonally_adjust,
    transform_bcb_series,
)


def _seasonal_series(n: int = 120, base: float = 0.4, amp: float = 0.8) -> pd.Series:
    """A monthly series = flat trend + a strong, purely seasonal sine."""
    idx = pd.date_range("2010-01-01", periods=n, freq="MS")
    values = base + amp * np.sin(2 * np.pi * idx.month / 12)
    return pd.Series(values, index=idx)


def _raw_bcb(name: str, group: str, n: int = 72) -> pd.DataFrame:
    idx = pd.date_range("2010-01-01", periods=n, freq="MS")
    return pd.DataFrame(
        {
            "date": idx,
            "value": 0.4 + 0.8 * np.sin(2 * np.pi * idx.month / 12),
            "source": "BCB/SGS",
            "sgs_code": 1,
            "series_name": name,
            "series_short_name": name,
            "series_group": group,
            "unit": "pct_mom",
        }
    )


def test_seasonally_adjust_removes_known_seasonality():
    pytest.importorskip("statsmodels")
    raw = _seasonal_series()
    sa = seasonally_adjust(raw)
    assert sa.notna().all()
    raw_by_month = raw.groupby(raw.index.month).mean()
    sa_by_month = sa.groupby(sa.index.month).mean()
    raw_spread = raw_by_month.max() - raw_by_month.min()
    sa_spread = sa_by_month.max() - sa_by_month.min()
    assert raw_spread > 1.0  # the input genuinely has a big seasonal swing
    assert sa_spread < 0.2 * raw_spread  # STL strips most of it


def test_seasonally_adjust_is_deterministic():
    pytest.importorskip("statsmodels")
    raw = _seasonal_series()
    pd.testing.assert_series_equal(seasonally_adjust(raw), seasonally_adjust(raw))


def test_seasonally_adjust_short_series_is_all_nan():
    out = seasonally_adjust(_seasonal_series(n=20))  # < _STL_MIN_OBS
    assert len(out) == 20
    assert out.isna().all()


def test_seasonally_adjust_without_statsmodels_is_all_nan(monkeypatch):
    # Simulate the build extra being absent: must degrade to NaN, never raise.
    monkeypatch.setattr(transforms, "_load_stl", lambda: None)
    out = seasonally_adjust(_seasonal_series())
    assert out.isna().all()


def test_seasonally_adjust_interior_gap_is_all_nan():
    pytest.importorskip("statsmodels")
    raw = _seasonal_series()
    raw.iloc[50] = np.nan  # a hole STL can't span
    out = seasonally_adjust(raw)
    assert out.isna().all()


def test_transform_bcb_series_adds_seasonal_columns_only_for_monthly_like():
    pytest.importorskip("statsmodels")
    raw = pd.concat(
        [_raw_bcb("IPCA", "headline"), _raw_bcb("Outra", "other")], ignore_index=True
    )
    out = transform_bcb_series(raw)
    assert {"mom_sa", "annualized_3m_sa"} <= set(out.columns)
    ipca = out[out["series_short_name"] == "IPCA"].sort_values("date")
    assert pd.notna(ipca["mom_sa"].iloc[-1])
    assert pd.notna(ipca["annualized_3m_sa"].iloc[-1])
    other = out[out["series_short_name"] == "Outra"]
    assert other["mom_sa"].isna().all()  # non-monthly-like group never gets SA


def test_build_core_metrics_carries_and_computes_seasonal_adjustment():
    pytest.importorskip("statsmodels")
    raw = pd.concat([_raw_bcb("EX0", "cores"), _raw_bcb("EX3", "cores")], ignore_index=True)
    bcb = transform_bcb_series(raw)
    config = {"core_sets": {"test": {"label": "Test", "members": ["EX0", "EX3"]}}}
    cores = build_core_metrics(bcb, config)
    assert {"mom_sa", "annualized_3m_sa"} <= set(cores.columns)
    # The aggregated mean row gets its own STL.
    mean = cores[cores["core_name"] == "Média"].sort_values("date")
    assert pd.notna(mean["mom_sa"].iloc[-1])
    # Members carry the SA computed upstream in transform_bcb_series.
    assert cores[cores["core_name"] == "EX0"]["mom_sa"].notna().any()
