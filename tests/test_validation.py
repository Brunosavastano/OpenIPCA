import pandas as pd

from ipca_dashboard.validation import (
    CRITICAL_SERIES,
    validate_critical_series_freshness,
    validate_ipca_items,
)


def _bcb_with_latest(per_series_latest: dict[str, str]) -> pd.DataFrame:
    """One row per series at its given latest month (plus an older row each)."""
    rows = []
    for name, latest in per_series_latest.items():
        rows.append({"series_short_name": name, "date": pd.Timestamp("2024-01-01"), "mom": 0.3})
        rows.append({"series_short_name": name, "date": pd.Timestamp(latest), "mom": 0.3})
    return pd.DataFrame(rows)


def test_freshness_pass_when_all_critical_series_current():
    bcb = _bcb_with_latest({s: "2024-06-01" for s in CRITICAL_SERIES})
    row = validate_critical_series_freshness(bcb).iloc[0]
    assert row["status"] == "pass"


def test_freshness_warns_when_a_critical_series_lags():
    latest = {s: "2024-06-01" for s in CRITICAL_SERIES}
    latest["Servicos"] = "2024-05-01"  # one month behind the global max
    bcb = _bcb_with_latest(latest)
    row = validate_critical_series_freshness(bcb).iloc[0]
    assert row["status"] == "warn"
    assert "Servicos" in str(row["value"])


def test_freshness_blocks_when_a_critical_series_is_absent():
    present = {s: "2024-06-01" for s in CRITICAL_SERIES if s != "EX3"}
    bcb = _bcb_with_latest(present)
    row = validate_critical_series_freshness(bcb).iloc[0]
    assert row["status"] == "block"
    assert "EX3" in str(row["value"])


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

