"""Navigate the IPCA classification hierarchy (group → subgroup → item → subitem).

The parent/child links already exist in the processed items
(`classification_code`, `parent_classification_code`, `level`) — see
fetch_ibge._level_from_classification / _parent_code. This module just reads them;
no new fetching.
"""

from __future__ import annotations

import pandas as pd

# Ordered hierarchy levels and the human label for each.
LEVEL_ORDER = ["group", "subgroup", "item", "subitem"]
LEVEL_LABEL_PT = {
    "group": "Grupo",
    "subgroup": "Subgrupo",
    "item": "Item",
    "subitem": "Subitem",
}


def child_level(level: str) -> str | None:
    """The level directly below `level`, or None if `level` is the deepest."""
    if level not in LEVEL_ORDER:
        return None
    idx = LEVEL_ORDER.index(level)
    return LEVEL_ORDER[idx + 1] if idx + 1 < len(LEVEL_ORDER) else None


def top_level_rows(items: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """All groups (top of the hierarchy) for the month, by contribution desc."""
    rows = items[(items["date"] == date) & (items["level"] == "group")].copy()
    return rows.sort_values("contribution_mom", ascending=False).reset_index(drop=True)


def children(items: pd.DataFrame, parent_code: str, date: pd.Timestamp) -> pd.DataFrame:
    """Direct children of `parent_code` in `date`, sorted by contribution desc.

    Returns the rows whose `parent_classification_code` == parent_code. Empty
    frame if the node has no children (e.g. a subitem, the deepest level).
    """
    if not parent_code:
        return items.iloc[0:0]
    rows = items[
        (items["date"] == date) & (items["parent_classification_code"] == parent_code)
    ].copy()
    return rows.sort_values("contribution_mom", ascending=False).reset_index(drop=True)


def node_label(items: pd.DataFrame, code: str, date: pd.Timestamp) -> str:
    """Human name of a node ('Alimentação e bebidas'), falling back to the code."""
    row = items[(items["date"] == date) & (items["classification_code"] == code)]
    if row.empty:
        return code
    return str(row.iloc[0].get("item_name", code))


def subitem_options(items: pd.DataFrame, date: pd.Timestamp) -> pd.DataFrame:
    """Subitems available in `date` as (classification_code, item_name), name-sorted.

    Feeds the "quanto subiu o meu item?" search box — the one-gesture answer to
    the question every visitor brings, instead of the 3-selectbox drilldown.
    """
    if items.empty or not {"date", "level", "classification_code", "item_name"}.issubset(
        items.columns
    ):
        return pd.DataFrame(columns=["classification_code", "item_name"])
    rows = items[(items["date"] == date) & (items["level"] == "subitem")]
    out = rows[["classification_code", "item_name"]].dropna()
    out = out.drop_duplicates("classification_code")
    return out.sort_values("item_name").reset_index(drop=True)
