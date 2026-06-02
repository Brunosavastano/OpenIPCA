import plotly.graph_objects as go
import pandas as pd

import ipca_dashboard.charts as charts
from ipca_dashboard.charts import (
    apply_layout,
    contribution_ranking,
    core_fan,
    core_lines,
    load_chart_theme,
    stacked_contribution,
)


def test_apply_layout_uses_theme_background_and_visible_title():
    fig = apply_layout(go.Figure(), "Título de teste", yaxis_title="p.p.")
    tpl = {**charts._DEFAULT_TEMPLATE, **load_chart_theme().get("plotly_template", {})}
    assert fig.layout.paper_bgcolor == tpl["paper_bgcolor"]
    assert "Título de teste" in fig.layout.title.text
    # Title font is the theme's text color — visible against the theme background,
    # whatever the palette (read from the module, not a hard-coded literal).
    assert fig.layout.title.font.color == charts._TEXT_COLOR


def test_core_lines_title_has_no_raw_metric_key():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "core_set_name": ["bcb_compact", "bcb_compact"],
            "core_name": ["EX0", "EX0"],
            "moving_average_3m": [0.4, 0.5],
        }
    )
    title = core_lines(df, "bcb_compact", "moving_average_3m").layout.title.text
    assert "moving_average_3m" not in title  # no raw key / underscores
    assert "média de 3 meses" in title  # friendly label instead


def test_core_fan_title_has_no_raw_metric_key():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-02-01", "2024-02-01"]),
            "core_set_name": ["bcb_compact"] * 4,
            "core_name": ["EX0", "EX3", "EX0", "EX3"],
            "moving_average_3m": [0.4, 0.6, 0.5, 0.7],
        }
    )
    fig = core_fan(df, "bcb_compact", "moving_average_3m")
    assert "moving_average_3m" not in fig.layout.title.text
    assert "média de 3 meses" in fig.layout.title.text
    assert fig.data[-1].line.color == charts._TEXT_COLOR


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
