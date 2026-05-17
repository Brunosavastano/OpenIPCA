import pandas as pd

from ipca_dashboard.validation import validate_ipca_items


def test_validate_group_contribution_matches_headline():
    df = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-01"),
                "classification_code": "",
                "level": "headline",
                "mom": 1.0,
                "weight": 100,
                "contribution_mom": 1.0,
            },
            {
                "date": pd.Timestamp("2024-01-01"),
                "classification_code": "1",
                "level": "group",
                "mom": 2.0,
                "weight": 50,
                "contribution_mom": 1.0,
            },
        ]
    )
    report = validate_ipca_items(df)
    row = report[report["check"] == "group_contribution_matches_headline"].iloc[0]
    assert row["status"] == "pass"

