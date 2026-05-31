import pandas as pd

from ipca_dashboard.charts import contribution_ranking


def _items(n: int, date: str = "2024-01-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime([date] * n),
            "level": ["group"] * n,
            "classification_code": [str(i) for i in range(n)],
            "item_name": [f"Grupo {i}" for i in range(n)],
            "contribution_mom": [float(i) - n / 2 for i in range(n)],
        }
    )


def _bar_count(fig) -> int:
    return len(fig.data[0].x)


def test_ranking_does_not_duplicate_when_few_categories():
    # 9 groups with top_n=10 must yield 9 bars, not 18 (the old bug).
    fig = contribution_ranking(_items(9), pd.Timestamp("2024-01-01"), "group", top_n=10)
    assert _bar_count(fig) == 9


def test_ranking_caps_and_dedupes_when_many_categories():
    # 25 items, top_n=10 -> at most 20 unique bars.
    fig = contribution_ranking(_items(25), pd.Timestamp("2024-01-01"), "group", top_n=10)
    assert _bar_count(fig) == 20


def test_ranking_boundary_exactly_two_top_n():
    # len(data) == 2*top_n -> show all, no duplication.
    fig = contribution_ranking(_items(20), pd.Timestamp("2024-01-01"), "group", top_n=10)
    assert _bar_count(fig) == 20
