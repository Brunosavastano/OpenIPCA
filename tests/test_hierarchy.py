"""Hierarchy navigation tests — pure, no network.

Uses the parent/child columns already in the processed items.
"""

import pandas as pd

from ipca_dashboard.hierarchy import (
    child_level,
    children,
    node_label,
    top_level_rows,
)

DATE = pd.Timestamp("2024-03-01")


def _items() -> pd.DataFrame:
    # group "1" -> subgroup "11" -> item "1101" -> subitem "1101001"
    rows = [
        {"classification_code": "1", "parent_classification_code": "", "level": "group",
         "item_name": "Alimentação e bebidas", "contribution_mom": 0.30, "weight": 20.0},
        {"classification_code": "2", "parent_classification_code": "", "level": "group",
         "item_name": "Transportes", "contribution_mom": 0.10, "weight": 18.0},
        {"classification_code": "11", "parent_classification_code": "1", "level": "subgroup",
         "item_name": "Alimentação no domicílio", "contribution_mom": 0.20, "weight": 12.0},
        {"classification_code": "12", "parent_classification_code": "1", "level": "subgroup",
         "item_name": "Alimentação fora", "contribution_mom": 0.10, "weight": 8.0},
        {"classification_code": "1101", "parent_classification_code": "11", "level": "item",
         "item_name": "Cereais", "contribution_mom": 0.05, "weight": 3.0},
        {"classification_code": "1101001", "parent_classification_code": "1101", "level": "subitem",
         "item_name": "Arroz", "contribution_mom": 0.03, "weight": 1.0},
    ]
    df = pd.DataFrame(rows)
    df["date"] = DATE
    return df


def test_child_level_order():
    assert child_level("group") == "subgroup"
    assert child_level("subgroup") == "item"
    assert child_level("item") == "subitem"
    assert child_level("subitem") is None


def test_top_level_rows_returns_groups_sorted():
    top = top_level_rows(_items(), DATE)
    assert list(top["level"].unique()) == ["group"]
    assert list(top["item_name"]) == ["Alimentação e bebidas", "Transportes"]  # by contrib desc


def test_children_returns_only_direct_children_sorted():
    kids = children(_items(), "1", DATE)
    assert list(kids["classification_code"]) == ["11", "12"]  # both subgroups of group 1
    assert list(kids["item_name"]) == ["Alimentação no domicílio", "Alimentação fora"]


def test_children_of_leaf_is_empty():
    assert children(_items(), "1101001", DATE).empty  # subitem has no children
    assert children(_items(), "", DATE).empty  # no parent code


def test_deep_chain_navigates_to_subitem():
    items = _items()
    assert list(children(items, "11", DATE)["classification_code"]) == ["1101"]
    assert list(children(items, "1101", DATE)["classification_code"]) == ["1101001"]


def test_node_label_returns_name_or_code():
    assert node_label(_items(), "1", DATE) == "Alimentação e bebidas"
    assert node_label(_items(), "999", DATE) == "999"  # unknown -> code
