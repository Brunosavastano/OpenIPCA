import math

import numpy as np
import pandas as pd

from ipca_dashboard.transforms import calculate_diffusion_from_items


def test_diffusion_excludes_missing_mom():
    # [1.0, -0.5, NaN] -> 1 positive out of 2 valid = 50.0 (NaN excluded), not 33.3.
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"] * 3),
            "level": ["subitem"] * 3,
            "mom": [1.0, -0.5, np.nan],
        }
    )
    out = calculate_diffusion_from_items(df, level="subitem")
    assert math.isclose(out["diffusion"].iloc[0], 50.0, rel_tol=1e-10)


def test_diffusion_by_group_excludes_missing():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"] * 4),
            "level": ["subitem"] * 4,
            "group_classification_code": ["1", "1", "2", "2"],
            "mom": [1.0, np.nan, -0.5, -0.5],
        }
    )
    out = calculate_diffusion_from_items(
        df, level="subitem", group_col="group_classification_code"
    )
    g1 = out[out["group_classification_code"] == "1"]["diffusion"].iloc[0]
    g2 = out[out["group_classification_code"] == "2"]["diffusion"].iloc[0]
    assert math.isclose(g1, 100.0, rel_tol=1e-10)  # 1 valid, positive (NaN dropped)
    assert math.isclose(g2, 0.0, rel_tol=1e-10)  # 2 valid, none positive


def test_diffusion_filters_by_level():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"] * 3),
            "level": ["subitem", "subitem", "group"],
            "mom": [1.0, -0.5, 1.0],
        }
    )
    out = calculate_diffusion_from_items(df, level="subitem")
    # Only the two subitem rows count -> 1 positive of 2 = 50.0.
    assert math.isclose(out["diffusion"].iloc[0], 50.0, rel_tol=1e-10)
