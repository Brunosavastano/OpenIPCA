import pandas as pd

from ipca_dashboard.alerts import evaluate_condition, generate_alerts


def test_evaluate_condition_basic_ops():
    assert evaluate_condition(5.1, ">", 5.0)
    assert evaluate_condition(5.0, ">=", 5.0)
    assert evaluate_condition(4.9, "<", 5.0)
    assert evaluate_condition(5.0, "between", [4.0, 6.0])
    assert evaluate_condition(7.0, "outside_band", [4.0, 6.0])


def test_generate_alerts_for_core_mean_threshold():
    dates = pd.date_range("2023-01-01", periods=30, freq="MS")
    bcb = pd.DataFrame(
        {
            "date": list(dates) * 2,
            "series_short_name": ["IPCA"] * len(dates) + ["Difusao"] * len(dates),
            "series_group": ["headline"] * len(dates) + ["diffusion"] * len(dates),
            "mom": [0.4] * len(dates) + [60.0] * len(dates),
            "rolling_12m": [4.0] * len(dates) + [None] * len(dates),
            "three_month_saar": [4.2] * len(dates) + [None] * len(dates),
            "moving_average_3m": [0.4] * len(dates) + [61.0] * len(dates),
            "percentile_since_2012": [50.0] * len(dates) + [70.0] * len(dates),
            "moving_average_3m_percentile": [50.0] * len(dates) + [85.0] * len(dates),
        }
    )
    cores = pd.DataFrame(
        {
            "date": dates,
            "core_set_name": ["bcb_compact"] * len(dates),
            "core_name": ["Média"] * len(dates),
            "mom": [0.4] * len(dates),
            "rolling_12m": [4.5] * len(dates),
            "three_month_saar": [5.3] * len(dates),
        }
    )
    rules = {
        "rules": [
            {
                "id": "core_high",
                "metric": "core_mean_3m_saar",
                "condition": ">",
                "threshold": 5.0,
                "severity": "high",
                "message": "core high",
            }
        ]
    }
    alerts = generate_alerts(rules, bcb, cores)
    assert len(alerts) == 1
    assert alerts.iloc[0]["alert_id"] == "core_high"
