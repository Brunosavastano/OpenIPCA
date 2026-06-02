import plotly.graph_objects as go
import pandas as pd

from ipca_dashboard.charts import (
    apply_layout,
    contribution_ranking,
    load_chart_theme,
    stacked_contribution,
)


def test_apply_layout_uses_theme_background_and_visible_title():
    fig = apply_layout(go.Figure(), "Título de teste", yaxis_title="p.p.")
    tpl = {**{"paper_bgcolor": "white", "plot_bgcolor": "white"},
           **load_chart_theme().get("plotly_template", {})}
    assert fig.layout.paper_bgcolor == tpl["paper_bgcolor"]
    assert "Título de teste" in fig.layout.title.text
    # Title font must be the dark text color (visible on the light theme bg).
    assert fig.layout.title.font.color == "#111827"


def test_apply_layout_subtitle_is_embedded():
    fig = apply_layout(go.Figure(), "T", subtitle="🔴 cima · 🔵 baixo")
    assert "cima" in fig.layout.title.text and "<sub>" in fig.layout.title.text


def test_stacked_contribution_axis_labels_not_swapped():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "level": ["group", "group"],
            "item_name": ["Alimentação e bebidas", "Alimentação e bebidas"],
            "contribution_mom": [0.2, 0.3],
        }
    )
    fig = stacked_contribution(df)
    assert fig.layout.xaxis.title.text == "Mês"
    assert "p.p." in fig.layout.yaxis.title.text  # not "Mês" on the Y axis


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
