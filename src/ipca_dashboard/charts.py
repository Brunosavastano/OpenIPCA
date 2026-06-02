from __future__ import annotations

from functools import lru_cache

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from ipca_dashboard.config import load_yaml

GROUP_COLORS = {
    "Alimentação e bebidas": "#B45309",
    "Habitação": "#7C3AED",
    "Artigos de residência": "#64748B",
    "Vestuário": "#DB2777",
    "Transportes": "#2563EB",
    "Saúde e cuidados pessoais": "#059669",
    "Despesas pessoais": "#B91C1C",
    "Educação": "#D97706",
    "Comunicação": "#4B5563",
}

# Fallback theme if config/chart_theme.yaml is missing — keeps charts working.
_DEFAULT_TEMPLATE = {
    "paper_bgcolor": "white",
    "plot_bgcolor": "white",
    "font_family": "Arial",
    "gridcolor": "#E5E7EB",
}
_TEXT_COLOR = "#111827"


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
        title=dict(text=title_text, x=0, xanchor="left", font=dict(size=18, color=_TEXT_COLOR)),
        paper_bgcolor=tpl["paper_bgcolor"],
        plot_bgcolor=tpl["plot_bgcolor"],
        font=dict(family=tpl["font_family"], size=13, color=_TEXT_COLOR),
        # Generous bottom margin so the horizontal legend never overlaps x labels.
        margin=dict(l=32, r=24, t=72, b=96),
        legend=dict(orientation="h", yanchor="top", y=-0.32, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False, automargin=True)
    fig.update_yaxes(gridcolor=tpl["gridcolor"], zerolinecolor="#9CA3AF", automargin=True)
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
    headline_value = float(headline["mom"].iloc[0]) if not headline.empty else groups["contribution_mom"].sum()
    x = groups["item_name"].tolist() + ["IPCA"]
    y = groups["contribution_mom"].tolist() + [headline_value]
    measure = ["relative"] * len(groups) + ["total"]
    fig = go.Figure(
        go.Waterfall(
            x=x,
            y=y,
            measure=measure,
            connector={"line": {"color": "#9CA3AF"}},
            increasing={"marker": {"color": "#B91C1C"}},
            decreasing={"marker": {"color": "#2563EB"}},
            totals={"marker": {"color": "#111827"}},
        )
    )
    return apply_layout(fig, f"Waterfall do IPCA - {date:%Y-%m}", "p.p.")


def contribution_ranking(ipca_items: pd.DataFrame, date: pd.Timestamp, level: str, top_n: int = 10) -> go.Figure:
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
    colors = ranking["contribution_mom"].map(lambda value: "#B91C1C" if value > 0 else "#2563EB")
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
    pivot = groups.pivot_table(index="item_name", columns="date", values="contribution_mom", aggfunc="first")
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


def core_lines(core_metrics: pd.DataFrame, core_set_name: str, metric: str = "rolling_12m") -> go.Figure:
    data = core_metrics[core_metrics["core_set_name"] == core_set_name].copy()
    data["core_name_display"] = data["core_name"].replace({"Media": "Média"})
    fig = px.line(
        data,
        x="date",
        y=metric,
        color="core_name_display",
        labels={"date": "Mês", metric: "%", "core_name_display": "Núcleo"},
    )
    return apply_layout(fig, f"Núcleos - {metric}", "%")


def core_fan(core_metrics: pd.DataFrame, core_set_name: str, metric: str = "rolling_12m") -> go.Figure:
    data = core_metrics[
        (core_metrics["core_set_name"] == core_set_name) & (~core_metrics["core_name"].isin(["Media", "Média"]))
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
            fillcolor="rgba(37,99,235,0.18)",
            line=dict(width=0),
            name="faixa min-max",
        )
    )
    fig.add_trace(go.Scatter(x=summary.index, y=summary["mean"], name="média", line=dict(color="#111827", width=2)))
    return apply_layout(fig, "Fan chart simples dos núcleos", "%")


def diffusion_line(bcb: pd.DataFrame) -> go.Figure:
    data = bcb[bcb["series_short_name"] == "Difusao"].sort_values("date")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["date"], y=data["mom"], name="mensal", line=dict(color="#047857", width=1.5)))
    fig.add_trace(
        go.Scatter(x=data["date"], y=data["moving_average_3m"], name="MM3M", line=dict(color="#111827", width=2.5))
    )
    if not data.empty:
        for p, color in [(20, "#D1D5DB"), (50, "#9CA3AF"), (80, "#F59E0B"), (90, "#DC2626")]:
            value = data["mom"].quantile(p / 100)
            fig.add_hline(y=value, line_dash="dot", line_color=color, annotation_text=f"p{p}")
    return apply_layout(fig, "Difusão do IPCA: mensal, MM3M e percentis", "% de subitens")


def ipca_diffusion_scatter(bcb: pd.DataFrame) -> go.Figure:
    ipca = bcb[bcb["series_short_name"] == "IPCA"][["date", "mom"]].rename(columns={"mom": "ipca_mom"})
    diff = bcb[bcb["series_short_name"] == "Difusao"][["date", "moving_average_3m"]].rename(
        columns={"moving_average_3m": "diffusion_mm3"}
    )
    data = ipca.merge(diff, on="date", how="inner").dropna()
    fig = px.scatter(
        data,
        x="ipca_mom",
        y="diffusion_mm3",
        color=data["date"].dt.year.astype(str),
        labels={"ipca_mom": "IPCA m/m (%)", "diffusion_mm3": "Difusão MM3M (%)", "color": "Ano"},
    )
    if not data.empty:
        fig.add_vline(x=data["ipca_mom"].median(), line_dash="dot", line_color="#9CA3AF")
        fig.add_hline(y=data["diffusion_mm3"].median(), line_dash="dot", line_color="#9CA3AF")
    return apply_layout(fig, "Quadrantes IPCA x difusão", "Difusão MM3M (%)")
