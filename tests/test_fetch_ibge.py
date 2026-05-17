import pandas as pd

from ipca_dashboard.fetch_ibge import normalize_sidra_7060


def test_normalize_sidra_7060_pivots_variables_and_levels():
    config = {
        "variables": {
            "mom": {"code": 63},
            "weight": {"code": 66},
        }
    }
    raw = pd.DataFrame(
        [
            {
                "D2C": "63",
                "D3C": "202604",
                "D4C": "7170",
                "D4N": "1.Alimentacao e bebidas",
                "V": "1.20",
                "source": "IBGE/SIDRA",
                "fetched_at": "test",
            },
            {
                "D2C": "66",
                "D3C": "202604",
                "D4C": "7170",
                "D4N": "1.Alimentacao e bebidas",
                "V": "21.5",
                "source": "IBGE/SIDRA",
                "fetched_at": "test",
            },
        ]
    )
    out = normalize_sidra_7060(raw, config)
    assert len(out) == 1
    assert out.iloc[0]["level"] == "group"
    assert out.iloc[0]["mom"] == 1.2
    assert out.iloc[0]["weight"] == 21.5

