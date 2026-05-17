import math

import pandas as pd

from ipca_dashboard.alerts import generate_alerts
from ipca_dashboard.audit import (
    build_alert_sensitivity_report,
    build_metric_window_report,
    build_reconciliation_report,
)
from ipca_dashboard.transforms import calc_rolling_12m, expanding_percentile, rolling_zscore, transform_ipca_items


def _synthetic_bcb(dates: pd.DatetimeIndex, mom: float = 1.0) -> pd.DataFrame:
    ipca = pd.DataFrame(
        {
            "date": dates,
            "source": "BCB/SGS",
            "sgs_code": 433,
            "series_name": "IPCA",
            "series_short_name": "IPCA",
            "series_group": "headline",
            "unit": "pct_mom",
            "mom": [mom] * len(dates),
        }
    )
    ipca["rolling_12m"] = calc_rolling_12m(ipca["mom"])
    ipca["three_month_saar"] = 0.0
    ipca["moving_average_3m"] = ipca["mom"].rolling(3, min_periods=3).mean()
    ipca["moving_average_6m"] = ipca["mom"].rolling(6, min_periods=6).mean()
    ipca["zscore_60m"] = rolling_zscore(ipca["mom"])
    ipca["percentile_since_2012"] = expanding_percentile(ipca["mom"])
    ipca["moving_average_3m_percentile"] = expanding_percentile(ipca["moving_average_3m"])
    ipca["fetched_at"] = "test"
    return ipca


def _synthetic_items(dates: pd.DatetimeIndex, mom: float = 1.0) -> pd.DataFrame:
    yoy = calc_rolling_12m(pd.Series([mom] * len(dates)))
    rows = []
    for idx, date in enumerate(dates):
        rows.append(
            {
                "date": date,
                "source": "IBGE/SIDRA",
                "item_code": "headline",
                "classification_code": "",
                "item_name": "Índice geral",
                "level": "headline",
                "parent_classification_code": "",
                "group_classification_code": "",
                "weight": 100.0,
                "mom": mom,
                "ytd": None,
                "yoy": yoy.iloc[idx],
                "fetched_at": "test",
            }
        )
        rows.append(
            {
                "date": date,
                "source": "IBGE/SIDRA",
                "item_code": "g1",
                "classification_code": "1",
                "item_name": "Grupo 1",
                "level": "group",
                "parent_classification_code": "",
                "group_classification_code": "1",
                "weight": 100.0,
                "mom": mom,
                "ytd": None,
                "yoy": yoy.iloc[idx],
                "fetched_at": "test",
            }
        )
        rows.append(
            {
                "date": date,
                "source": "IBGE/SIDRA",
                "item_code": "s1",
                "classification_code": "1000001",
                "item_name": "Subitem 1",
                "level": "subitem",
                "parent_classification_code": "1",
                "group_classification_code": "1",
                "weight": 100.0,
                "mom": mom,
                "ytd": None,
                "yoy": yoy.iloc[idx],
                "fetched_at": "test",
            }
        )
    return transform_ipca_items(pd.DataFrame(rows))


def test_reconciliation_matches_official_12m_and_contributions():
    dates = pd.date_range("2020-01-01", periods=30, freq="MS")
    bcb = _synthetic_bcb(dates)
    items = _synthetic_items(dates)

    report = build_reconciliation_report(bcb, items)
    checks = report.set_index("check")

    assert checks.loc["ipca_12m_calc_vs_sidra", "status"] == "pass"
    assert checks.loc["group_contribution_vs_headline", "status"] == "pass"
    assert checks.loc["group_chain_12m_vs_headline_12m", "status"] == "pass"
    assert checks.loc["group_chain_12m_vs_headline_12m", "max_abs_diff"] <= 0.05


def test_metric_window_report_flags_insufficient_zscore_window():
    dates = pd.date_range("2024-01-01", periods=10, freq="MS")
    bcb = _synthetic_bcb(dates)
    cores = pd.DataFrame(
        {
            "date": dates,
            "core_set_name": ["bcb_compact"] * len(dates),
            "core_name": ["Média"] * len(dates),
            "mom": [0.3] * len(dates),
            "rolling_12m": [None] * len(dates),
            "three_month_saar": [None] * len(dates),
            "moving_average_3m": [None] * len(dates),
            "zscore_60m": [None] * len(dates),
            "percentile_since_2012": [None] * len(dates),
        }
    )

    report = build_metric_window_report(bcb, cores)
    zscore = report[(report["entity"] == "IPCA") & (report["metric"] == "zscore_60m")].iloc[0]

    assert zscore["status"] == "insuficiente"
    assert zscore["min_required_months"] == 24


def test_zscore_and_percentile_respect_minimum_sample():
    series = pd.Series(range(23), dtype=float)
    assert rolling_zscore(series).isna().all()
    assert expanding_percentile(series).isna().all()

    longer = pd.Series(range(24), dtype=float)
    assert math.isclose(expanding_percentile(longer).iloc[-1], 100.0)


def test_alerts_do_not_fire_with_insufficient_history():
    dates = pd.date_range("2024-01-01", periods=10, freq="MS")
    bcb = _synthetic_bcb(dates)
    diffusion = bcb.copy()
    diffusion["series_short_name"] = "Difusao"
    diffusion["series_name"] = "Difusão"
    diffusion["series_group"] = "diffusion"
    diffusion["mom"] = 80.0
    bcb = pd.concat([bcb, diffusion], ignore_index=True)
    cores = pd.DataFrame(
        {
            "date": dates,
            "core_set_name": ["bcb_compact"] * len(dates),
            "core_name": ["Média"] * len(dates),
            "mom": [0.7] * len(dates),
            "rolling_12m": [5.5] * len(dates),
            "three_month_saar": [8.0] * len(dates),
        }
    )
    rules = {
        "rules": [
            {
                "id": "core_high",
                "metric": "core_mean_3m_saar",
                "condition": ">",
                "threshold": 5.0,
            }
        ]
    }

    alerts = generate_alerts(rules, bcb, cores, min_history_months=24)
    assert alerts.empty


def test_alert_sensitivity_classifies_window_sensitive_rules():
    dates = pd.date_range("2019-01-01", periods=90, freq="MS")
    bcb = _synthetic_bcb(dates)
    diffusion = bcb.copy()
    diffusion["series_short_name"] = "Difusao"
    diffusion["series_name"] = "Difusão"
    diffusion["series_group"] = "diffusion"
    diffusion["mom"] = list([90.0] * 30 + [40.0] * 59 + [90.0])
    diffusion["moving_average_3m"] = diffusion["mom"].rolling(3, min_periods=3).mean()
    bcb = pd.concat([bcb, diffusion], ignore_index=True)
    cores = pd.DataFrame(
        {
            "date": dates,
            "core_set_name": ["bcb_compact"] * len(dates),
            "core_name": ["Média"] * len(dates),
            "mom": [0.3] * len(dates),
            "rolling_12m": [4.0] * len(dates),
            "three_month_saar": [4.0] * len(dates),
        }
    )
    rules = {
        "rules": [
            {
                "id": "diffusion_high",
                "metric": "diffusion_mm3_percentile",
                "condition": ">",
                "threshold": 80,
            }
        ]
    }

    report = build_alert_sensitivity_report(rules, bcb, cores)
    assert report["classification"].iloc[0] in {"validado", "sensível à janela"}
    assert set(report["window"]) == {"full_sample", "since_2020", "rolling_60m"}

