"""get_item_weights: question-aware basket-weight evidence (Q&A only, never raises)."""

import pandas as pd

from ipca_dashboard.ai.tools import get_item_weights


def _items() -> pd.DataFrame:
    date = pd.Timestamp("2026-05-01")
    rows = [
        ("11", "group", "Alimentação e bebidas", 21.59),
        ("1101001", "subitem", "Arroz", 0.50),
        ("2102001", "subitem", "Passagem aérea", 0.67),
        ("3103001", "subitem", "Gasolina", 5.34),
        ("4104001", "subitem", "Sal", 0.04),
        ("0", "headline", "Índice geral", 100.0),
    ]
    return pd.DataFrame(
        [
            {"date": date, "classification_code": c, "level": lvl, "item_name": n, "weight": w}
            for c, lvl, n, w in rows
        ]
    )


def test_matches_named_items_with_their_weights():
    ev = get_item_weights("Passagem aérea e arroz têm pesos diferentes no IPCA?", _items())
    by = {e.metric: e.value for e in ev}
    assert by == {"Peso na cesta: Passagem aérea": 0.67, "Peso na cesta: Arroz": 0.50}
    assert all(e.evidence_id.startswith("ev_weight_") and e.unit == "%" for e in ev)


def test_matches_multiword_item_with_extra_spacing_and_string_dates():
    items = _items()
    extra = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-05-01"),
                "classification_code": "5105001",
                "level": "subitem",
                "item_name": "Leite longa vida",
                "weight": 0.42,
            }
        ]
    )
    items = pd.concat([items, extra], ignore_index=True)
    items["date"] = items["date"].dt.strftime("%Y-%m-%d")
    ev = get_item_weights("leite     longa vida", items)
    assert [e.metric for e in ev] == ["Peso na cesta: Leite longa vida"]
    assert ev[0].date == "2026-05"


def test_no_item_named_returns_empty():
    assert get_item_weights("Como está a difusão da inflação?", _items()) == []


def test_word_boundary_avoids_substring_false_positive():
    # "Sal" must not fire inside "salário" (the #69 lesson, applied to item names).
    assert get_item_weights("O salário acompanhou a inflação?", _items()) == []


def test_headline_level_is_never_injected():
    # "Índice geral" is the headline (weight 100) -> excluded even if named, and
    # "IPCA" must not inject the index weight either.
    assert get_item_weights("Qual o índice geral?", _items()) == []
    assert all(e.value != 100.0 for e in get_item_weights("o que move o ipca?", _items()))


def test_cap_keeps_the_heaviest_matches():
    ev = get_item_weights("arroz gasolina passagem aérea sal", _items(), max_items=2)
    assert {e.metric for e in ev} == {"Peso na cesta: Gasolina", "Peso na cesta: Passagem aérea"}


def test_never_raises_on_empty_or_missing_data():
    assert get_item_weights("arroz", pd.DataFrame()) == []
    assert get_item_weights("", _items()) == []
    assert get_item_weights("arroz", _items().drop(columns=["weight"])) == []
    assert get_item_weights("arroz", _items().drop(columns=["date"])) == []
    assert get_item_weights("arroz", _items().drop(columns=["item_name"])) == []
    assert get_item_weights("arroz", _items().drop(columns=["classification_code"])) == []
