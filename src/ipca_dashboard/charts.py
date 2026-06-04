from __future__ import annotations

from functools import lru_cache

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ipca_dashboard.config import load_yaml
from ipca_dashboard.glossary import metric_label

GROUP_COLORS = {
    "Alimentação e bebidas": "#E8943A",
    "Habitação": "#9B7FE0",
    "Artigos de residência": "#5FB7C4",
    "Vestuário": "#DD6B5C",
    "Transportes": "#4A8FE0",
    "Saúde e cuidados pessoais": "#35B07D",
    "Despesas pessoais": "#C77FB0",
    "Educação": "#E6C84A",
    "Comunicação": "#7E8896",
}

# Institutional terminal palette (Bloomberg/Aladdin direction). Inflation
# semantics: up = bad = red, down = good = green.
_UP = "#E5484D"  # inflation accelerates / upward contribution
_DOWN = "#35B07D"  # decelerates / downward contribution
_INFO = "#4A8FE0"  # metric identity / informational line, not value direction
_MONO = "IBM Plex Mono"
_MUTED = "#8A93A3"  # axis ticks / secondary text

# Categorical sequence for series that are colored by category but NOT covered by
# an explicit map. Without this, Plotly Express falls back to its bright default
# colorway (the generic blue/red/green/purple), which clashes with the
# institutional palette. Passed as color_discrete_sequence to every px.* call.
_SEQ = [
    "#E6EAF1",
    "#4A8FE0",
    "#9B7FE0",
    "#E8943A",
    "#35B07D",
    "#5FB7C4",
    "#DD6B5C",
    "#E6C84A",
    "#C77FB0",
    "#7E8896",
]
# Núcleos: reserve white/bold for the "Média" line (applied after the figure is
# built), so the individual cores read as distinct mid-tones, not a pure-white
# line fighting the mean for attention.
_CORE_SEQ = ["#4A8FE0", "#9B7FE0", "#E8943A", "#35B07D", "#5FB7C4", "#DD6B5C", "#E6C84A"]

# Fallback theme if config/chart_theme.yaml is missing — keeps charts working.
_DEFAULT_TEMPLATE = {
    # Transparent so each chart shows its card background (#11161F) seamlessly.
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font_family": "IBM Plex Sans, sans-serif",
    "gridcolor": "#1A222D",
}
_TEXT_COLOR = "#E6EAF1"  # light text, visible on the dark chart background


@lru_cache(maxsize=1)
def load_chart_theme() -> dict:
    """Single source of chart styling (spec_V3 §253). Reads config/chart_theme.yaml."""
    try:
        return load_yaml("chart_theme.yaml")
    except Exception:  # noqa: BLE001 - missing/invalid config must not break charts
        return {"plotly_template": _DEFAULT_TEMPLATE, "palette": {}}


def theme_palette() -> dict:
    return load_chart_theme().get("palette", {})


def apply_layout(
    fig: go.Figure,
    title: str,
    yaxis_title: str | None = None,
    xaxis_title: str | None = None,
    subtitle: str | None = None,
) -> go.Figure:
    tpl = {**_DEFAULT_TEMPLATE, **load_chart_theme().get("plotly_template", {})}
    # Optional subtitle rendered under the title (used to explain the heatmap colors).
    title_text = title if not subtitle else f"{title}<br><sub>{subtitle}</sub>"
    fig.update_layout(
        title=dict(
            text=title_text,
            x=0,
            xanchor="left",
            font=dict(family=tpl["font_family"], size=15, color=_TEXT_COLOR),
        ),
        paper_bgcolor=tpl["paper_bgcolor"],
        plot_bgcolor=tpl["plot_bgcolor"],
        font=dict(family=tpl["font_family"], size=12, color=_MUTED),
        # Institutional colorway for any trace without an explicit color (belt-and-
        # suspenders; px.* charts also pass color_discrete_sequence directly).
        colorway=_SEQ,
        # Generous bottom margin so the horizontal legend never overlaps x labels.
        margin=dict(l=32, r=24, t=70, b=96),
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.32,
            xanchor="left",
            x=0,
            font=dict(size=11, color="#B7BECB"),
        ),
        hovermode="x unified",
        hoverlabel=dict(
            font=dict(family=_MONO, color=_TEXT_COLOR), bgcolor="#11161F", bordercolor="#2E3845"
        ),
    )
    # Numbers in a mono, tabular face — the "terminal" feel.
    fig.update_xaxes(
        showgrid=False,
        automargin=True,
        linecolor="#222A36",
        tickfont=dict(family=_MONO, size=11, color=_MUTED),
    )
    fig.update_yaxes(
        gridcolor=tpl["gridcolor"],
        zerolinecolor="#2E3845",
        automargin=True,
        tickfont=dict(family=_MONO, size=11, color=_MUTED),
    )
    if yaxis_title:
        fig.update_yaxes(title=yaxis_title)
    if xaxis_title:
        fig.update_xaxes(title=xaxis_title)
    return fig


def stacked_contribution(ipca_items: pd.DataFrame, months: int = 24) -> go.Figure:
    groups = ipca_items[ipca_items["level"] == "group"].sort_values("date")
    groups = groups[groups["date"] >= groups["date"].max() - pd.DateOffset(months=months - 1)]
    fig = px.bar(
        groups,
        x="date",
        y="contribution_mom",
        color="item_name",
        color_discrete_map=GROUP_COLORS,
        color_discrete_sequence=_SEQ,  # fallback for any group missing from the map
        labels={"date": "Mês", "contribution_mom": "Contribuição (p.p.)", "item_name": "Grupo"},
    )
    # Quarterly ticks + angled short dates so labels fit on narrow screens.
    fig.update_xaxes(dtick="M3", tickformat="%b/%y", tickangle=-45)
    fig = apply_layout(
        fig,
        f"Contribuição mensal por grupo (últimos {months} meses)",
        yaxis_title="Contribuição (p.p.)",
        xaxis_title="Mês",
    )
    return fig


def waterfall_latest(ipca_items: pd.DataFrame, date: pd.Timestamp) -> go.Figure:
    groups = ipca_items[(ipca_items["level"] == "group") & (ipca_items["date"] == date)].copy()
    groups = groups.sort_values("contribution_mom", ascending=False)
    headline = ipca_items[(ipca_items["level"] == "headline") & (ipca_items["date"] == date)]
    headline_value = (
        float(headline["mom"].iloc[0]) if not headline.empty else groups["contribution_mom"].sum()
    )
    x = groups["item_name"].tolist() + ["IPCA"]
    y = groups["contribution_mom"].tolist() + [headline_value]
    measure = ["relative"] * len(groups) + ["total"]
    fig = go.Figure(
        go.Waterfall(
            x=x,
            y=y,
            measure=measure,
            connector={"line": {"color": _MUTED}},
            increasing={"marker": {"color": _UP}},
            decreasing={"marker": {"color": _DOWN}},
            totals={"marker": {"color": _TEXT_COLOR}},
        )
    )
    return apply_layout(fig, f"Waterfall do IPCA - {date:%Y-%m}", "p.p.")


def contribution_ranking(
    ipca_items: pd.DataFrame, date: pd.Timestamp, level: str, top_n: int = 10
) -> go.Figure:
    data = ipca_items[(ipca_items["date"] == date) & (ipca_items["level"] == level)].copy()
    data = data.dropna(subset=["contribution_mom"])
    if len(data) <= 2 * top_n:
        # Few categories: show them all once, never duplicated.
        ranking = data.sort_values("contribution_mom")
    else:
        ranking = (
            pd.concat(
                [
                    data.nsmallest(top_n, "contribution_mom"),
                    data.nlargest(top_n, "contribution_mom"),
                ]
            )
            .drop_duplicates(subset=["date", "classification_code"])
            .sort_values("contribution_mom")
        )
    colors = ranking["contribution_mom"].map(lambda value: _UP if value > 0 else _DOWN)
    fig = go.Figure(
        go.Bar(
            x=ranking["contribution_mom"],
            y=ranking["item_name"],
            orientation="h",
            marker_color=colors,
            hovertemplate="%{y}<br>%{x:.2f} p.p.<extra></extra>",
        )
    )
    level_pt = {"group": "grupo", "subgroup": "subgrupo", "item": "item", "subitem": "subitem"}
    return apply_layout(
        fig,
        f"Maiores pressões de alta e de baixa — por {level_pt.get(level, level)}",
        yaxis_title="",
        xaxis_title="Contribuição (p.p.)",
    )


def heatmap_groups(ipca_items: pd.DataFrame, months: int = 24) -> go.Figure:
    groups = ipca_items[ipca_items["level"] == "group"].sort_values("date")
    groups = groups[groups["date"] >= groups["date"].max() - pd.DateOffset(months=months - 1)]
    pivot = groups.pivot_table(
        index="item_name", columns="date", values="contribution_mom", aggfunc="first"
    )
    # Order rows so the groups that pushed inflation the most sit on top.
    pivot = pivot.reindex(pivot.mean(axis=1).sort_values(ascending=True).index)
    x_labels = [d.strftime("%b/%y") for d in pivot.columns]
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=x_labels,
            y=pivot.index,
            colorscale="RdBu_r",
            zmid=0,
            colorbar={
                "title": "Contribuição<br>(p.p.)",
                "ticksuffix": " p.p.",
            },
            hovertemplate="<b>%{y}</b><br>%{x}<br>%{z:.2f} p.p.<extra></extra>",
        )
    )
    return apply_layout(
        fig,
        f"Mapa de calor: contribuição por grupo (últimos {months} meses)",
        yaxis_title="Grupo",
        xaxis_title="Mês",
        subtitle="🔴 vermelho = puxou a inflação para cima · 🔵 azul = segurou para baixo",
    )


def core_lines(
    core_metrics: pd.DataFrame, core_set_name: str, metric: str = "rolling_12m"
) -> go.Figure:
    data = core_metrics[core_metrics["core_set_name"] == core_set_name].copy()
    data["core_name_display"] = data["core_name"].replace({"Media": "Média"})
    fig = px.line(
        data,
        x="date",
        y=metric,
        color="core_name_display",
        color_discrete_sequence=_CORE_SEQ,
        labels={"date": "Mês", metric: "%", "core_name_display": "Núcleo"},
    )
    # Make the mean the hero line (thick, near-white) and thin the individual
    # cores, matching the institutional terminal mockup.
    for trace in fig.data:
        if trace.name in ("Média", "Media"):
            trace.line.color = _TEXT_COLOR
            trace.line.width = 2.6
        else:
            trace.line.width = 1.3
    return apply_layout(
        fig, f"Núcleos — {metric_label(metric)}", yaxis_title="%", xaxis_title="Mês"
    )


def core_fan(
    core_metrics: pd.DataFrame, core_set_name: str, metric: str = "rolling_12m"
) -> go.Figure:
    data = core_metrics[
        (core_metrics["core_set_name"] == core_set_name)
        & (~core_metrics["core_name"].isin(["Media", "Média"]))
    ]
    pivot = data.pivot_table(index="date", columns="core_name", values=metric)
    summary = pd.DataFrame(
        {
            "min": pivot.min(axis=1),
            "max": pivot.max(axis=1),
            "mean": pivot.mean(axis=1),
        }
    ).dropna()
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=summary.index,
            y=summary["max"],
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=summary.index,
            y=summary["min"],
            fill="tonexty",
            fillcolor="rgba(74,143,224,0.14)",
            line=dict(width=0),
            name="faixa min-max",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=summary.index,
            y=summary["mean"],
            name="média",
            line=dict(color=_TEXT_COLOR, width=2.4),
        )
    )
    return apply_layout(
        fig,
        f"Dispersão dos núcleos — {metric_label(metric)}",
        yaxis_title="%",
        xaxis_title="Mês",
        subtitle="faixa azul = do menor ao maior núcleo · linha = média dos núcleos",
    )


def diffusion_line(bcb: pd.DataFrame) -> go.Figure:
    data = bcb[bcb["series_short_name"] == "Difusao"].sort_values("date")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=data["date"], y=data["mom"], name="mensal", line=dict(color=_INFO, width=1.3))
    )
    fig.add_trace(
        go.Scatter(
            x=data["date"],
            y=data["moving_average_3m"],
            name="MM3M",
            line=dict(color=_TEXT_COLOR, width=2.4),
        )
    )
    if not data.empty:
        for p, color in [(20, _DOWN), (50, _MUTED), (80, "#E0A046"), (90, _UP)]:
            value = data["mom"].quantile(p / 100)
            fig.add_hline(y=value, line_dash="dot", line_color=color, annotation_text=f"p{p}")
    return apply_layout(fig, "Difusão do IPCA: mensal, MM3M e percentis", "% de subitens")


def ipca_diffusion_scatter(bcb: pd.DataFrame) -> go.Figure:
    ipca = bcb[bcb["series_short_name"] == "IPCA"][["date", "mom"]].rename(
        columns={"mom": "ipca_mom"}
    )
    diff = bcb[bcb["series_short_name"] == "Difusao"][["date", "moving_average_3m"]].rename(
        columns={"moving_average_3m": "diffusion_mm3"}
    )
    data = ipca.merge(diff, on="date", how="inner").dropna()
    fig = px.scatter(
        data,
        x="ipca_mom",
        y="diffusion_mm3",
        color=data["date"].dt.year.astype(str),
        color_discrete_sequence=_SEQ,
        labels={"ipca_mom": "IPCA m/m (%)", "diffusion_mm3": "Difusão MM3M (%)", "color": "Ano"},
    )
    if not data.empty:
        fig.add_vline(x=data["ipca_mom"].median(), line_dash="dot", line_color=_MUTED)
        fig.add_hline(y=data["diffusion_mm3"].median(), line_dash="dot", line_color=_MUTED)
    return apply_layout(fig, "Quadrantes IPCA x difusão", "Difusão MM3M (%)")
