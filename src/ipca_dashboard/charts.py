from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


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


def apply_layout(fig: go.Figure, title: str, yaxis_title: str | None = None) -> go.Figure:
    fig.update_layout(
        title=title,
        template="plotly_white",
        font=dict(family="Arial", size=13, color="#111827"),
        title_font=dict(size=18, color="#111827"),
        margin=dict(l=32, r=24, t=64, b=48),
        legend=dict(orientation="h", yanchor="bottom", y=-0.28, xanchor="left", x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#E5E7EB", zerolinecolor="#9CA3AF")
    if yaxis_title:
        fig.update_yaxes(title=yaxis_title)
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
        labels={"date": "Mês", "contribution_mom": "p.p.", "item_name": "Grupo"},
    )
    return apply_layout(fig, "Contribuição mensal por grupo do IPCA", "p.p.")


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
    top = data.nlargest(top_n, "contribution_mom")
    bottom = data.nsmallest(top_n, "contribution_mom")
    ranking = pd.concat([bottom, top]).sort_values("contribution_mom")
    colors = ranking["contribution_mom"].map(lambda value: "#B91C1C" if value > 0 else "#2563EB")
    fig = go.Figure(go.Bar(x=ranking["contribution_mom"], y=ranking["item_name"], orientation="h", marker_color=colors))
    return apply_layout(fig, f"Top pressões altistas e baixistas - {level}", "p.p.")


def heatmap_groups(ipca_items: pd.DataFrame, months: int = 24) -> go.Figure:
    groups = ipca_items[ipca_items["level"] == "group"].sort_values("date")
    groups = groups[groups["date"] >= groups["date"].max() - pd.DateOffset(months=months - 1)]
    pivot = groups.pivot_table(index="item_name", columns="date", values="contribution_mom", aggfunc="first")
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=[d.strftime("%Y-%m") for d in pivot.columns],
            y=pivot.index,
            colorscale="RdBu_r",
            zmid=0,
            colorbar={"title": "p.p."},
        )
    )
    return apply_layout(fig, "Heatmap de contribuição por grupo", "Grupo")


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
