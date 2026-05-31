import math

import numpy as np
import pandas as pd

from ipca_dashboard.transforms import build_core_metrics

MEMBER_COLS = [
    "rolling_12m",
    "three_month_saar",
    "moving_average_3m",
    "zscore_60m",
    "percentile_since_2012",
]


def _cores_bcb(members_by_date: dict[str, list[str]]) -> pd.DataFrame:
    """Build a minimal BCB 'cores' frame: {date: [present member names]}."""
    rows = []
    for date_str, present in members_by_date.items():
        for name in present:
            row = {
                "date": pd.Timestamp(date_str),
                "series_group": "cores",
                "series_short_name": name,
                "mom": 0.40,
            }
            for col in MEMBER_COLS:
                row[col] = 0.0
            rows.append(row)
    return pd.DataFrame(rows)


def test_core_mean_complete_set_is_marked_complete():
    dates = ["2024-01-01", "2024-02-01"]
    bcb = _cores_bcb({d: ["EX0", "EX3"] for d in dates})
    config = {"core_sets": {"s": {"label": "S", "members": ["EX0", "EX3"]}}}

    out = build_core_metrics(bcb, config)
    mean = out[out["core_name"] == "Média"]

    assert (mean["is_complete_core_set"]).all()
    assert (mean["n_members_available"] == 2).all()
    assert (mean["n_members_expected"] == 2).all()
    # Both members present and equal -> mean equals the member value.
    assert math.isclose(mean.sort_values("date")["mom"].iloc[0], 0.40, rel_tol=1e-9)


def test_core_mean_missing_member_no_keyerror_and_flagged_incomplete():
    # EX3 is entirely absent from the data -> must not raise, must be flagged.
    dates = ["2024-01-01", "2024-02-01"]
    bcb = _cores_bcb({d: ["EX0"] for d in dates})
    config = {"core_sets": {"s": {"label": "S", "members": ["EX0", "EX3"]}}}

    out = build_core_metrics(bcb, config)  # must not raise KeyError
    mean = out[out["core_name"] == "Média"].sort_values("date")

    assert not mean["is_complete_core_set"].any()
    assert (mean["n_members_available"] == 1).all()
    assert (mean["missing_members"] == "EX3").all()
    # Incomplete -> mean omitted (NaN), not a silent partial average.
    assert mean["mom"].isna().all()


def test_core_mean_partial_month_is_incomplete_only_that_month():
    # EX3 present in Jan but missing in Feb.
    bcb = _cores_bcb({"2024-01-01": ["EX0", "EX3"], "2024-02-01": ["EX0"]})
    config = {"core_sets": {"s": {"label": "S", "members": ["EX0", "EX3"]}}}

    out = build_core_metrics(bcb, config)
    mean = out[out["core_name"] == "Média"].sort_values("date").reset_index(drop=True)

    assert bool(mean.loc[0, "is_complete_core_set"]) is True
    assert bool(mean.loc[1, "is_complete_core_set"]) is False
    assert math.isclose(mean.loc[0, "mom"], 0.40, rel_tol=1e-9)
    assert np.isnan(mean.loc[1, "mom"])
