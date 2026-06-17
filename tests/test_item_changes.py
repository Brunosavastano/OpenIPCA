"""get_item_changes: question-aware item variation evidence (Q&A only, never raises)."""

import pandas as pd

from ipca_dashboard.ai.tools import _match_named_items, get_item_changes


def _items() -> pd.DataFrame:
    date = pd.Timestamp("2026-05-01")
    rows = [
        # code, level, name, weight, mom, yoy, contribution_mom
        ("3103001", "subitem", "Gasolina", 5.34, -1.46, 5.43, -0.08),
        ("1101001", "subitem", "Café moído", 0.59, -2.38, -12.25, -0.01),
        ("1101002", "subitem", "Arroz", 0.50, 1.74, -16.92, 0.01),
        ("4104001", "subitem", "Sal", 0.04, 0.30, 2.10, 0.00),
        ("0", "headline", "Índice geral", 100.0, 0.58, 4.72, 0.58),
    ]
    return pd.DataFrame(
        [
            {
                "date": date, "classification_code": c, "level": lvl, "item_name": n,
                "weight": w, "mom": mom, "yoy": yoy, "contribution_mom": cm,
            }
            for c, lvl, n, w, mom, yoy, cm in rows
        ]
    )


def test_named_item_emits_mom_12m_and_contribution():
    ev = get_item_changes("Quanto subiu o café moído?", _items())
    vals = {e.evidence_id: (e.value, e.unit) for e in ev}
    assert vals["ev_item_mom_1101001"] == (-2.38, "%")
    assert vals["ev_item_12m_1101001"] == (-12.25, "%")
    assert vals["ev_item_contrib_1101001"] == (-0.01, "p.p.")


def test_matches_multiword_item_with_extra_spacing_and_string_dates():
    items = _items()
    items["date"] = items["date"].dt.strftime("%Y-%m-%d")
    ev = get_item_changes("café     moído", items)
    assert ev[0].evidence_id == "ev_item_mom_1101001"
    assert ev[0].date == "2026-05"


def test_no_item_named_returns_empty():
    assert get_item_changes("Como está a difusão da inflação?", _items()) == []


def test_word_boundary_avoids_substring_false_positive():
    assert get_item_changes("O salário acompanhou a inflação?", _items()) == []


def test_headline_level_is_never_injected():
    assert get_item_changes("Qual o índice geral?", _items()) == []


def test_cap_keeps_the_heaviest_item():
    ev = get_item_changes("gasolina e arroz subiram?", _items(), max_items=1)
    # one item (the heaviest, gasolina) -> exactly its 3 metrics
    assert len(ev) == 3
    assert all("3103001" in e.evidence_id for e in ev)


def test_missing_metric_column_degrades_to_none():
    ev = get_item_changes("gasolina", _items().drop(columns=["yoy"]))
    by = {e.evidence_id: e.value for e in ev}
    assert by["ev_item_12m_3103001"] is None
    assert by["ev_item_mom_3103001"] == -1.46


def test_never_raises_on_empty_or_missing_data():
    assert get_item_changes("café", pd.DataFrame()) == []
    assert get_item_changes("", _items()) == []
    assert get_item_changes("café", _items().drop(columns=["weight"])) == []
    assert get_item_changes("café", _items().drop(columns=["date"])) == []
    assert get_item_changes("café", _items().drop(columns=["item_name"])) == []
    assert get_item_changes("café", _items().drop(columns=["classification_code"])) == []


def test_shared_matcher_never_raises_on_malformed_data():
    malformed = _items().astype({"weight": "object"})
    malformed.at[0, "weight"] = {"bad": "value"}
    assert _match_named_items("gasolina", malformed, max_items=4) == []
    assert _match_named_items("gasolina", _items(), max_items="bad") == []
