from __future__ import annotations

import operator
from typing import Any

import pandas as pd

OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

ALERT_COLUMNS = [
    "date",
    "reference_month",
    "alert_id",
    "metric",
    "value",
    "threshold",
    "condition",
    "severity",
    "message",
    "status",
    "created_at",
]


def evaluate_condition(value: float, condition: str, threshold: Any) -> bool:
    if pd.isna(value):
        return False
    if condition in OPS:
        return OPS[condition](float(value), float(threshold))
    if condition == "between":
        low, high = threshold
        return float(low) <= float(value) <= float(high)
    if condition == "outside_band":
        low, high = threshold
        return float(value) < float(low) or float(value) > float(high)
    raise ValueError(f"Unsupported alert condition: {condition}")


def build_metric_snapshot(
    bcb: pd.DataFrame,
    core_metrics: pd.DataFrame,
    core_set_name: str = "bcb_compact",
) -> tuple[pd.Timestamp, dict[str, float]]:
    latest_date = pd.to_datetime(bcb["date"]).max()
    metrics: dict[str, float] = {}

    core_latest = core_metrics[
        (core_metrics["core_set_name"] == core_set_name)
        & (core_metrics["date"] == latest_date)
    ]
    core_mean = core_latest[core_latest["core_name"].isin(["Media", "Média"])]
    if not core_mean.empty:
        row = core_mean.iloc[0]
        metrics["core_mean_mom"] = row["mom"]
        metrics["core_mean_12m"] = row["rolling_12m"]
        metrics["core_mean_3m_saar"] = row["three_month_saar"]
    core_members = core_latest[~core_latest["core_name"].isin(["Media", "Média"])]
    if not core_members.empty:
        metrics["core_any_3m_saar"] = core_members["three_month_saar"].max()

    latest_bcb = bcb[bcb["date"] == latest_date]
    for _, row in latest_bcb.iterrows():
        prefix = str(row["series_short_name"])
        metrics[f"{prefix}_mom"] = row["mom"]
        metrics[f"{prefix}_12m"] = row["rolling_12m"]
        metrics[f"{prefix}_3m_saar"] = row["three_month_saar"]
        metrics[f"{prefix}_mm3"] = row["moving_average_3m"]
        metrics[f"{prefix}_percentile"] = row["percentile_since_2012"]
        metrics[f"{prefix}_mm3_percentile"] = row["moving_average_3m_percentile"]

    services = latest_bcb[latest_bcb["series_short_name"] == "Servicos"]
    if not services.empty:
        row = services.iloc[0]
        metrics["services_3m_saar_minus_services_12m"] = row["three_month_saar"] - row["rolling_12m"]

    ipca = latest_bcb[latest_bcb["series_short_name"] == "IPCA"]
    diffusion = latest_bcb[latest_bcb["series_short_name"] == "Difusao"]
    if not ipca.empty and not diffusion.empty:
        ipca_pctl = ipca.iloc[0]["percentile_since_2012"]
        diffusion_mm3_pctl = diffusion.iloc[0]["moving_average_3m_percentile"]
        metrics["localized_shock_score"] = float(ipca_pctl > 80 and diffusion_mm3_pctl < 50)
        metrics["diffusion_mm3_percentile"] = diffusion_mm3_pctl

    return latest_date, metrics


def generate_alerts(
    rules_config: dict[str, Any],
    bcb: pd.DataFrame,
    core_metrics: pd.DataFrame,
    core_set_name: str = "bcb_compact",
    min_history_months: int = 24,
) -> pd.DataFrame:
    if bcb.empty or core_metrics.empty:
        return pd.DataFrame(columns=ALERT_COLUMNS)
    if pd.to_datetime(bcb["date"]).nunique() < min_history_months:
        return pd.DataFrame(columns=ALERT_COLUMNS)
    reference_date, metrics = build_metric_snapshot(bcb, core_metrics, core_set_name)
    # Anchor the alert's timestamps to the DATA (the reference month), not the wall
    # clock. The alerts table is versioned and refreshed by an Action; a wall-clock
    # value would make the file differ on every run and produce phantom commits even
    # when no inflation number changed. Deterministic data -> commit only on real change.
    created_at = pd.Timestamp(reference_date).isoformat()
    rows: list[dict[str, Any]] = []
    for rule in rules_config.get("rules", []):
        metric = rule["metric"]
        if metric not in metrics:
            continue
        value = metrics[metric]
        if evaluate_condition(value, rule["condition"], rule["threshold"]):
            rows.append(
                {
                    "date": reference_date,
                    "reference_month": reference_date.strftime("%Y-%m"),
                    "alert_id": rule["id"],
                    "metric": metric,
                    "value": float(value),
                    "threshold": rule["threshold"],
                    "condition": rule["condition"],
                    "severity": rule.get("severity", "info"),
                    "message": rule.get("message", rule["id"]),
                    "status": "active",
                    "created_at": created_at,
                }
            )
    return pd.DataFrame(rows, columns=ALERT_COLUMNS)
