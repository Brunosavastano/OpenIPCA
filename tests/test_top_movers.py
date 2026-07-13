"""Vilões e aliados do mês: top subitems by official monthly variation.

The selection must be a PURE, declared rule (weight floor + mom ranking) — no
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


def test_ranks_up_and_down_by_mom_even_when_yoy_disagrees():
    items = _items(
        [
            ("Cenoura", 54.9, 2.0, 0.5),
            ("Transporte por aplicativo", 28.5, 12.0, 0.6),
            ("Energia", 10.3, 0.2, 4.0),
            ("Arroz", -21.6, -1.0, 0.6),
            ("Feijão", -10.0, -5.0, 0.4),
            ("Pão", 5.0, 0.3, 0.9),
        ]
    )
    up, down = top_movers(items, DATE, n=2)
    assert list(up["item_name"]) == ["Transporte por aplicativo", "Cenoura"]
    assert list(down["item_name"]) == ["Feijão", "Arroz"]


def test_can_rank_up_and_down_by_yoy_instead():
    items = _items(
        [
            ("Cenoura", 54.9, 2.0, 0.5),
            ("Passagem aérea", 28.5, 12.0, 0.6),
            ("Arroz", -21.6, -1.0, 0.6),
            ("Feijão", -10.0, -5.0, 0.4),
        ]
    )
    up, down = top_movers(items, DATE, n=2, rank_by="yoy")
    assert list(up["item_name"]) == ["Cenoura", "Passagem aérea"]
    assert list(down["item_name"]) == ["Arroz", "Feijão"]


def test_invalid_ranking_falls_back_to_monthly():
    items = _items([("Maior no mês", 1.0, 8.0, 0.5), ("Maior em 12m", 9.0, 2.0, 0.5)])
    up, _ = top_movers(items, DATE, rank_by="unknown")
    assert list(up["item_name"]) == ["Maior no mês", "Maior em 12m"]


def test_weight_floor_is_a_pure_declared_rule():
    items = _items(
        [
            ("Pepino", 43.3, 8.1, 0.0033),  # real case: big yoy, negligible weight
            ("Energia", 10.3, 0.2, 4.0),
        ]
    )
    up, _ = top_movers(items, DATE, n=5, min_weight=0.1)
    assert list(up["item_name"]) == ["Energia"]  # weight floor excludes curiosities


def test_rows_without_yoy_keep_the_monthly_ranking():
    items = _items([("Novo subitem", None, 1.0, 0.5), ("Energia", 10.3, 0.2, 4.0)])
    up, down = top_movers(items, DATE, n=5)
    assert list(up["item_name"]) == ["Novo subitem", "Energia"]
    assert down.empty


def test_missing_yoy_column_keeps_rows_and_adds_empty_context():
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
    assert list(up["item_name"]) == ["Arroz"]
    assert up["yoy"].isna().all()
    assert down.empty


def test_missing_mom_column_yields_empty_frames():
    items = pd.DataFrame(
        {
            "date": [DATE],
            "level": ["subitem"],
            "item_name": ["Arroz"],
            "yoy": [-10.0],
            "weight": [1.0],
        }
    )
    up, down = top_movers(items, DATE)
    assert up.empty and down.empty


def test_none_limit_returns_every_eligible_row_split_by_monthly_sign():
    items = _items(
        [(f"Alta {i}", float(i), float(i), 0.5) for i in range(1, 8)]
        + [(f"Queda {i}", -float(i), -float(i), 0.5) for i in range(1, 7)]
        + [("Estável", 3.0, 0.0, 0.5)]
    )
    up, down = top_movers(items, DATE, n=None)
    assert len(up) == 7
    assert len(down) == 6
    assert up.iloc[0]["item_name"] == "Alta 7"
    assert down.iloc[0]["item_name"] == "Queda 6"


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
