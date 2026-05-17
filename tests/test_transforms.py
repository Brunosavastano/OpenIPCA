import math

import pandas as pd

from ipca_dashboard.transforms import calc_3m_saar, transform_ipca_items


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

