import plotly.graph_objects as go
import pandas as pd

import ipca_dashboard.charts as charts
from ipca_dashboard.charts import (
    apply_layout,
    contribution_ranking,
    core_fan,
    core_lines,
    diffusion_line,
    heatmap_groups,
    load_chart_theme,
    momentum_line,
    stacked_contribution,
    waterfall_latest,
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


def test_momentum_line_shows_nsa_and_sa_traces():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            "series_short_name": ["IPCA"] * 3,
            "mom": [0.40, 0.55, 0.30],
            "mom_sa": [0.42, 0.38, 0.40],
        }
    )
    fig = momentum_line(df)
    assert len(fig.data) == 2
    names = " ".join(tr.name for tr in fig.data)
    assert "NSA" in names and "SA" in names
    # The seasonally adjusted line is the hero (theme text color), like diffusion's MM3M.
    sa_trace = next(tr for tr in fig.data if "ajuste sazonal" in tr.name)
    assert sa_trace.line.color == charts._TEXT_COLOR


def test_momentum_line_degrades_when_sa_column_is_absent():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
            "series_short_name": ["IPCA"] * 3,
            "mom": [0.40, 0.55, 0.30],
        }
    )
    fig = momentum_line(df)
    assert len(fig.data) == 1
    assert fig.data[0].name == "m/m (NSA)"
    assert "ajuste sazonal" not in fig.layout.title.text


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
            "mom": [1.0, 1.4],
        }
    )
    fig = stacked_contribution(df)
    assert fig.layout.xaxis.title.text == "Mês"
    assert "p.p." in fig.layout.yaxis.title.text  # not "Mês" on the Y axis


def test_stacked_contribution_hover_shows_variation_and_contribution():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
            "level": ["group", "group"],
            "item_name": ["Alimentação e bebidas", "Alimentação e bebidas"],
            "contribution_mom": [0.2, 0.3],
            "mom": [1.0, 1.4],
        }
    )
    fig = stacked_contribution(df)
    template = fig.data[0].hovertemplate
    assert "variação" in template and "%" in template
    assert "p.p." in template
    assert fig.data[0].customdata is not None


def _items(n: int, date: str = "2024-01-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime([date] * n),
            "level": ["group"] * n,
            "classification_code": [str(i) for i in range(n)],
            "item_name": [f"Grupo {i}" for i in range(n)],
            "contribution_mom": [float(i) - n / 2 for i in range(n)],
            "mom": [float(i) + 0.5 for i in range(n)],  # variation (%), real data always carries it
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


def test_directional_colors_are_consistent_across_inflation_charts():
    items = _items(4)
    items = pd.concat(
        [
            items,
            pd.DataFrame(
                [
                    {
                        "date": pd.Timestamp("2024-01-01"),
                        "level": "headline",
                        "classification_code": "headline",
                        "item_name": "IPCA",
                        "contribution_mom": 0.0,
                        "mom": 1.0,
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    waterfall = waterfall_latest(items, pd.Timestamp("2024-01-01"))
    assert waterfall.data[0].increasing.marker.color == charts._UP
    assert waterfall.data[0].decreasing.marker.color == charts._DOWN

    ranking = contribution_ranking(items, pd.Timestamp("2024-01-01"), "group", top_n=10)
    colors = dict(zip(ranking.data[0].y, ranking.data[0].marker.color, strict=False))
    assert colors["Grupo 3"] == charts._UP
    assert colors["Grupo 0"] == charts._DOWN

    bcb = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=5, freq="MS"),
            "series_short_name": ["Difusao"] * 5,
            "mom": [20.0, 40.0, 60.0, 80.0, 90.0],
            "moving_average_3m": [None, None, 40.0, 60.0, 75.0],
        }
    )
    diffusion = diffusion_line(bcb)
    assert diffusion.data[0].line.color != charts._DOWN
    assert diffusion.layout.shapes[0].line.color == charts._DOWN
    assert diffusion.layout.shapes[-1].line.color == charts._UP


def _items_with_headline(n: int, headline_mom: float = 1.0) -> pd.DataFrame:
    items = _items(n)
    headline = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-01"),
                "level": "headline",
                "classification_code": "headline",
                "item_name": "IPCA",
                "contribution_mom": 0.0,
                "mom": headline_mom,
            }
        ]
    )
    return pd.concat([items, headline], ignore_index=True)


def test_ranking_hover_shows_variation_and_contribution():
    # The hover must carry BOTH the variation (%) and the contribution (p.p.) so
    # the two units are never confused (the whole point of this view).
    fig = contribution_ranking(_items(5), pd.Timestamp("2024-01-01"), "group", top_n=10)
    template = fig.data[0].hovertemplate
    assert "Variação" in template and "%" in template
    assert "Contribuição" in template and "p.p." in template
    assert fig.data[0].customdata is not None  # variation (mom) rides on customdata
    # X axis stays the contribution in p.p. (the additive, correct unit).
    assert fig.layout.xaxis.title.text == "Contribuição (p.p.)"


def test_waterfall_hover_and_axis_show_variation_and_contribution():
    fig = waterfall_latest(_items_with_headline(3), pd.Timestamp("2024-01-01"))
    template = fig.data[0].hovertemplate
    assert "Variação" in template and "%" in template
    assert "Contribuição" in template and "p.p." in template
    assert fig.data[0].customdata is not None
    # Y axis is now unambiguous ("Contribuição (p.p.)", not a bare "p.p.").
    assert fig.layout.yaxis.title.text == "Contribuição (p.p.)"


def test_heatmap_customdata_matches_z_grid():
    df = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-01"),
                "level": "group",
                "item_name": "Grupo B",
                "contribution_mom": 0.10,
                "mom": 1.0,
            },
            {
                "date": pd.Timestamp("2024-02-01"),
                "level": "group",
                "item_name": "Grupo B",
                "contribution_mom": 0.30,
                "mom": 3.0,
            },
            {
                "date": pd.Timestamp("2024-01-01"),
                "level": "group",
                "item_name": "Grupo A",
                "contribution_mom": 0.40,
                "mom": 4.0,
            },
            {
                "date": pd.Timestamp("2024-02-01"),
                "level": "group",
                "item_name": "Grupo A",
                "contribution_mom": 0.20,
                "mom": 2.0,
            },
        ]
    )
    fig = heatmap_groups(df, months=24)
    trace = fig.data[0]
    assert trace.hovertemplate and "Variação" in trace.hovertemplate
    # Rows are sorted by mean contribution ascending. The variation customdata
    # must follow that same row/column order, cell-for-cell with z.
    assert list(trace.y) == ["Grupo B", "Grupo A"]
    assert trace.z.tolist() == [[0.10, 0.30], [0.40, 0.20]]
    assert trace.customdata.tolist() == [[1.0, 3.0], [4.0, 2.0]]
