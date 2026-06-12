"""'Quanto subiu o meu item?' — subitem options + sparkline helpers."""

import pandas as pd

from ipca_dashboard.charts import subitem_sparkline
from ipca_dashboard.hierarchy import subitem_options

DATE = pd.Timestamp("2026-04-01")


def _items() -> pd.DataFrame:
    rows = []
    for month in ("2026-03-01", "2026-04-01"):
        date = pd.Timestamp(month)
        rows.extend(
            [
                {"date": date, "level": "subitem", "classification_code": "7201001",
                 "item_name": "Gasolina", "mom": 0.5, "yoy": 8.0, "weight": 4.5},
                {"date": date, "level": "subitem", "classification_code": "1101001",
                 "item_name": "Arroz", "mom": -1.0, "yoy": -21.6, "weight": 0.6},
                {"date": date, "level": "group", "classification_code": "7",
                 "item_name": "Transportes", "mom": 0.06, "yoy": 3.0, "weight": 20.6},
            ]
        )
    return pd.DataFrame(rows)


def test_options_are_subitems_of_the_month_sorted_by_name():
    options = subitem_options(_items(), DATE)
    assert list(options["item_name"]) == ["Arroz", "Gasolina"]  # sorted, no group rows
    assert list(options["classification_code"]) == ["1101001", "7201001"]


def test_options_dedupe_and_tolerate_missing_columns():
    duplicated = pd.concat([_items(), _items()], ignore_index=True)
    options = subitem_options(duplicated, DATE)
    assert len(options) == 2  # one row per classification_code
    assert subitem_options(pd.DataFrame(), DATE).empty
    assert subitem_options(pd.DataFrame({"date": [DATE]}), DATE).empty


def test_sparkline_titles_with_the_item_name_and_plots_mom():
    fig = subitem_sparkline(_items(), "7201001")
    assert "Gasolina" in fig.layout.title.text
    assert "% m/m" in fig.layout.yaxis.title.text
    assert len(fig.data[0].x) == 2  # both months plotted


def test_sparkline_unknown_code_returns_valid_empty_figure():
    fig = subitem_sparkline(_items(), "9999999")
    assert "9999999" in fig.layout.title.text  # falls back to the code
    assert len(fig.data[0].x) == 0
