import pandas as pd

from ipca_dashboard.diagnostics import build_diagnostic_text


def test_diagnostic_text_uses_mm3_not_nsa_annualized_core_momentum():
    date = pd.Timestamp("2024-03-01")
    bcb = pd.DataFrame(
        [
            {
                "date": date,
                "series_short_name": "IPCA",
                "mom": 0.30,
                "rolling_12m": 4.50,
            },
            {
                "date": date,
                "series_short_name": "Difusao",
                "mom": 60.0,
                "moving_average_3m": 55.0,
            },
        ]
    )
    items = pd.DataFrame(
        [
            {
                "date": date,
                "level": "group",
                "item_name": "Grupo A",
                "contribution_mom": 0.20,
            },
            {
                "date": date,
                "level": "group",
                "item_name": "Grupo B",
                "contribution_mom": -0.10,
            },
        ]
    )
    cores = pd.DataFrame(
        [
            {
                "date": date,
                "core_set_name": "bcb_compact",
                "core_name": "Média",
                "mom": 0.40,
                "moving_average_3m": 0.50,
                "three_month_saar": 999.0,
                "rolling_12m": 5.0,
            }
        ]
    )

    text = build_diagnostic_text(bcb, items, cores, pd.DataFrame())["diagnostic"]

    assert "0.50% em MM3M (NSA)" in text
    assert "3m anualizado" not in text
    assert "999.00" not in text


def test_diagnostic_uses_readable_alert_message_not_raw_id():
    date = pd.Timestamp("2024-03-01")
    bcb = pd.DataFrame(
        [
            {"date": date, "series_short_name": "IPCA", "mom": 0.30, "rolling_12m": 4.50,
             "moving_average_3m": 0.40},
            {"date": date, "series_short_name": "Difusao", "mom": 60.0, "moving_average_3m": 55.0},
        ]
    )
    items = pd.DataFrame(
        [{"date": date, "level": "group", "item_name": "Grupo A", "contribution_mom": 0.20}]
    )
    cores = pd.DataFrame(
        [{"date": date, "core_set_name": "bcb_compact", "core_name": "Média",
          "mom": 0.40, "moving_average_3m": 0.50, "rolling_12m": 5.0}]
    )
    alerts = pd.DataFrame(
        [{"alert_id": "core_mean_3m_saar_high", "severity": "high",
          "message": "Média dos núcleos acima do limite."}]
    )

    text = build_diagnostic_text(bcb, items, cores, alerts)["diagnostic"]

    # Readable message used; raw machine id never leaks into the prose.
    assert "Média dos núcleos acima do limite." in text
    assert "core_mean_3m_saar_high" not in text
