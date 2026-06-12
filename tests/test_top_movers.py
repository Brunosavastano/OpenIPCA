"""Vilões e aliados do mês: top subitems by official 12m variation.

The selection must be a PURE, declared rule (weight floor + yoy ranking) — no
hand-curated list — and degrade to empty frames (card omitted) on missing data.
"""

import pandas as pd

from ipca_dashboard.transforms import top_movers

DATE = pd.Timestamp("2026-04-01")


def _items(rows: list[tuple[str, float | None, float, float]]) -> pd.DataFrame:
    """rows: (item_name, yoy, mom, weight) — all subitems on DATE."""
    return pd.DataFrame(
        {
            "date": [DATE] * len(rows),
            "level": ["subitem"] * len(rows),
            "item_name": [r[0] for r in rows],
            "yoy": [r[1] for r in rows],
            "mom": [r[2] for r in rows],
            "weight": [r[3] for r in rows],
        }
    )


def test_ranks_up_and_down_by_yoy():
    items = _items(
        [
            ("Cenoura", 54.9, 26.6, 0.5),
            ("Transporte por aplicativo", 28.5, 1.0, 0.6),
            ("Energia", 10.3, 0.2, 4.0),
            ("Arroz", -21.6, -1.0, 0.6),
            ("Feijão", -10.0, -0.5, 0.4),
            ("Pão", 5.0, 0.3, 0.9),
        ]
    )
    up, down = top_movers(items, DATE, n=2)
    assert list(up["item_name"]) == ["Cenoura", "Transporte por aplicativo"]
    assert list(down["item_name"]) == ["Arroz", "Feijão"]


def test_weight_floor_is_a_pure_declared_rule():
    items = _items(
        [
            ("Pepino", 43.3, 8.1, 0.0033),  # real case: big yoy, negligible weight
            ("Energia", 10.3, 0.2, 4.0),
        ]
    )
    up, _ = top_movers(items, DATE, n=5, min_weight=0.1)
    assert list(up["item_name"]) == ["Energia"]  # weight floor excludes curiosities


def test_rows_without_yoy_are_excluded_not_crashing():
    items = _items([("Novo subitem", None, 1.0, 0.5), ("Energia", 10.3, 0.2, 4.0)])
    up, down = top_movers(items, DATE, n=5)
    assert list(up["item_name"]) == ["Energia"]
    assert list(down["item_name"]) == ["Energia"]


def test_missing_yoy_column_yields_empty_frames():
    items = pd.DataFrame(
        {
            "date": [DATE],
            "level": ["subitem"],
            "item_name": ["Arroz"],
            "mom": [0.5],
            "weight": [1.0],
        }
    )
    up, down = top_movers(items, DATE)
    assert up.empty and down.empty


def test_empty_input_yields_empty_frames():
    up, down = top_movers(pd.DataFrame(), DATE)
    assert up.empty and down.empty


def test_only_subitems_of_the_requested_month_count():
    items = pd.concat(
        [
            _items([("Energia", 10.3, 0.2, 4.0)]),
            _items([("Gasolina", 99.0, 9.0, 5.0)]).assign(date=pd.Timestamp("2026-03-01")),
            _items([("Alimentação e bebidas", 88.0, 8.0, 20.0)]).assign(level="group"),
        ],
        ignore_index=True,
    )
    up, _ = top_movers(items, DATE)
    assert list(up["item_name"]) == ["Energia"]  # other month and group level excluded
