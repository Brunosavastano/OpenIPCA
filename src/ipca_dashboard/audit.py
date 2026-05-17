from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from typing import Any

import numpy as np
import pandas as pd

from ipca_dashboard.alerts import build_metric_snapshot, evaluate_condition, generate_alerts
from ipca_dashboard.config import OUTPUTS_DIR, load_yaml
from ipca_dashboard.fetch_bcb import fetch_all_sgs
from ipca_dashboard.fetch_ibge import fetch_sidra_7060, normalize_sidra_7060
from ipca_dashboard.io import write_csv
from ipca_dashboard.transforms import (
    build_core_metrics,
    calc_rolling_12m,
    expanding_percentile,
    transform_bcb_series,
    transform_ipca_items,
)
from ipca_dashboard.validation import validate_all


LOGGER = logging.getLogger(__name__)
AUDIT_DIR = OUTPUTS_DIR / "audit"


@dataclass(frozen=True)
class AuditOutputs:
    coverage: Path = AUDIT_DIR / "coverage_report.csv"
    reconciliation: Path = AUDIT_DIR / "reconciliation_report.csv"
    metric_windows: Path = AUDIT_DIR / "metric_window_report.csv"
    alert_sensitivity: Path = AUDIT_DIR / "alert_sensitivity_report.csv"
    report: Path = AUDIT_DIR / "econometric_accuracy_report.md"


METRIC_MIN_PERIODS = {
    "mom": 1,
    "rolling_12m": 12,
    "three_month_saar": 3,
    "moving_average_3m": 3,
    "moving_average_6m": 6,
    "zscore_60m": 24,
    "percentile_since_2012": 24,
    "moving_average_3m_percentile": 24,
}


def _expected_months(first: pd.Timestamp, last: pd.Timestamp) -> int:
    if pd.isna(first) or pd.isna(last):
        return 0
    return len(pd.period_range(first.to_period("M"), last.to_period("M"), freq="M"))


def build_coverage_report(bcb: pd.DataFrame, ipca_items: pd.DataFrame, core_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for short_name, group in bcb.groupby("series_short_name", sort=True):
        dates = pd.to_datetime(group["date"]).dropna()
        first, last = dates.min(), dates.max()
        expected = _expected_months(first, last)
        unique_months = dates.dt.to_period("M").nunique()
        rows.append(
            {
                "dataset": "BCB/SGS",
                "entity": short_name,
                "label": group["series_name"].iloc[0],
                "first_date": first.date() if pd.notna(first) else None,
                "last_date": last.date() if pd.notna(last) else None,
                "observations": len(group),
                "unique_months": unique_months,
                "expected_months": expected,
                "missing_months": max(expected - unique_months, 0),
                "duplicates": int(group.duplicated(["series_short_name", "date"]).sum()),
            }
        )

    for level, group in ipca_items.groupby("level", sort=True):
        dates = pd.to_datetime(group["date"]).dropna()
        first, last = dates.min(), dates.max()
        expected = _expected_months(first, last)
        unique_months = dates.dt.to_period("M").nunique()
        rows.append(
            {
                "dataset": "IBGE/SIDRA 7060",
                "entity": level,
                "label": f"{level} ({group['classification_code'].nunique()} códigos)",
                "first_date": first.date() if pd.notna(first) else None,
                "last_date": last.date() if pd.notna(last) else None,
                "observations": len(group),
                "unique_months": unique_months,
                "expected_months": expected,
                "missing_months": max(expected - unique_months, 0),
                "duplicates": int(group.duplicated(["date", "classification_code"]).sum()),
            }
        )

    for key, group in core_metrics.groupby(["core_set_name", "core_name"], sort=True):
        dates = pd.to_datetime(group["date"]).dropna()
        first, last = dates.min(), dates.max()
        expected = _expected_months(first, last)
        unique_months = dates.dt.to_period("M").nunique()
        rows.append(
            {
                "dataset": "Núcleos derivados",
                "entity": f"{key[0]}:{key[1]}",
                "label": key[1],
                "first_date": first.date() if pd.notna(first) else None,
                "last_date": last.date() if pd.notna(last) else None,
                "observations": len(group),
                "unique_months": unique_months,
                "expected_months": expected,
                "missing_months": max(expected - unique_months, 0),
                "duplicates": int(group.duplicated(["date"]).sum()),
            }
        )
    return pd.DataFrame(rows)


def _summary_row(
    check: str,
    reference: str,
    compared: str,
    observations: int,
    max_abs_diff: float | None,
    mean_abs_diff: float | None,
    tolerance: float | None,
    status: str,
    notes: str,
) -> dict[str, object]:
    return {
        "check": check,
        "reference": reference,
        "compared": compared,
        "observations": observations,
        "max_abs_diff": max_abs_diff,
        "mean_abs_diff": mean_abs_diff,
        "tolerance": tolerance,
        "status": status,
        "notes": notes,
    }


def _status_from_diff(max_abs_diff: float | None, tolerance: float, warn_tolerance: float | None = None) -> str:
    if max_abs_diff is None or pd.isna(max_abs_diff):
        return "insuficiente"
    if max_abs_diff <= tolerance:
        return "pass"
    if warn_tolerance is not None and max_abs_diff <= warn_tolerance:
        return "warn"
    return "fail"


def build_reconciliation_report(bcb: pd.DataFrame, ipca_items: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    sidra_headline = (
        ipca_items[ipca_items["level"] == "headline"][["date", "mom", "yoy"]]
        .drop_duplicates("date")
        .rename(columns={"mom": "sidra_mom", "yoy": "sidra_yoy"})
    )
    sgs_ipca = (
        bcb[bcb["series_short_name"] == "IPCA"][["date", "mom", "rolling_12m"]]
        .drop_duplicates("date")
        .rename(columns={"mom": "sgs_mom", "rolling_12m": "sgs_rolling_12m"})
    )

    monthly = sgs_ipca.merge(sidra_headline, on="date", how="inner").dropna(subset=["sgs_mom", "sidra_mom"])
    if monthly.empty:
        rows.append(_summary_row("ipca_mom_sgs_vs_sidra", "SIDRA headline 63", "SGS 433", 0, None, None, 0.01, "insuficiente", "Sem interseção mensal."))
    else:
        diff = monthly["sgs_mom"] - monthly["sidra_mom"]
        max_diff = float(diff.abs().max())
        rows.append(
            _summary_row(
                "ipca_mom_sgs_vs_sidra",
                "SIDRA headline 63",
                "SGS 433",
                len(monthly),
                round(max_diff, 6),
                round(float(diff.abs().mean()), 6),
                0.01,
                _status_from_diff(max_diff, 0.01, 0.03),
                "Compara variação mensal oficial entre fontes.",
            )
        )

    official_12m = sgs_ipca.merge(sidra_headline, on="date", how="inner").dropna(subset=["sgs_rolling_12m", "sidra_yoy"])
    if official_12m.empty:
        rows.append(_summary_row("ipca_12m_calc_vs_sidra", "SIDRA headline 2265", "12m composto SGS", 0, None, None, 0.03, "insuficiente", "Sem janela 12m completa."))
    else:
        diff = official_12m["sgs_rolling_12m"] - official_12m["sidra_yoy"]
        max_diff = float(diff.abs().max())
        rows.append(
            _summary_row(
                "ipca_12m_calc_vs_sidra",
                "SIDRA headline 2265",
                "12m composto SGS",
                len(official_12m),
                round(max_diff, 6),
                round(float(diff.abs().mean()), 6),
                0.03,
                _status_from_diff(max_diff, 0.03, 0.08),
                "Diferenças pequenas podem refletir arredondamento mensal.",
            )
        )

    group_sum = (
        ipca_items[ipca_items["level"] == "group"].groupby("date", as_index=False)["contribution_mom"].sum()
        .rename(columns={"contribution_mom": "group_contribution_sum"})
    )
    contribution = sidra_headline.merge(group_sum, on="date", how="inner").dropna(subset=["sidra_mom", "group_contribution_sum"])
    if contribution.empty:
        rows.append(_summary_row("group_contribution_vs_headline", "SIDRA headline 63", "Soma contribuições grupos", 0, None, None, 0.02, "insuficiente", "Sem grupos para comparar."))
    else:
        diff = contribution["group_contribution_sum"] - contribution["sidra_mom"]
        max_diff = float(diff.abs().max())
        rows.append(
            _summary_row(
                "group_contribution_vs_headline",
                "SIDRA headline 63",
                "Soma contribuições grupos",
                len(contribution),
                round(max_diff, 6),
                round(float(diff.abs().mean()), 6),
                0.02,
                _status_from_diff(max_diff, 0.02, 0.05),
                "Tolerância alinhada ao SPEC; acima de 0,05 p.p. é bloqueante.",
            )
        )

    group_chain = (
        ipca_items[ipca_items["level"] == "group"]
        .groupby("date")["contribution_12m_chain"]
        .sum(min_count=1)
        .reset_index()
        .rename(columns={"contribution_12m_chain": "group_chain_sum"})
    )
    chain = sidra_headline.merge(group_chain, on="date", how="inner").dropna(subset=["sidra_yoy", "group_chain_sum"])
    if chain.empty:
        rows.append(_summary_row("group_chain_12m_vs_headline_12m", "SIDRA headline 2265", "Soma contribuição 12m encadeada", 0, None, None, 0.05, "insuficiente", "Sem janela encadeada completa."))
    else:
        diff = chain["group_chain_sum"] - chain["sidra_yoy"]
        max_diff = float(diff.abs().max())
        rows.append(
            _summary_row(
                "group_chain_12m_vs_headline_12m",
                "SIDRA headline 2265",
                "Soma contribuição 12m encadeada",
                len(chain),
                round(max_diff, 6),
                round(float(diff.abs().mean()), 6),
                0.05,
                _status_from_diff(max_diff, 0.05, 0.12),
                "Audita a decomposição 12m encadeada por grupos.",
            )
        )

    diffusion = bcb[bcb["series_short_name"] == "Difusao"][["date", "mom"]].rename(columns={"mom": "official_diffusion"})
    subitems = ipca_items[ipca_items["level"] == "subitem"].copy()
    subitems["positive"] = subitems["mom"] > 0
    calculated_diffusion = (
        subitems.groupby("date", as_index=False)["positive"].mean().assign(calculated_diffusion=lambda d: d["positive"] * 100)
        [["date", "calculated_diffusion"]]
    )
    diff_join = diffusion.merge(calculated_diffusion, on="date", how="inner").dropna()
    if diff_join.empty:
        rows.append(_summary_row("official_vs_calculated_diffusion", "SGS 21379", "Difusão calculada por subitem", 0, None, None, None, "insuficiente", "Sem interseção de difusão."))
    else:
        gap = diff_join["official_diffusion"] - diff_join["calculated_diffusion"]
        corr = diff_join["official_diffusion"].corr(diff_join["calculated_diffusion"])
        rows.append(
            _summary_row(
                "official_vs_calculated_diffusion",
                "SGS 21379",
                "Difusão calculada por subitem",
                len(diff_join),
                round(float(gap.abs().max()), 6),
                round(float(gap.abs().mean()), 6),
                None,
                "reference_only",
                f"Métricas conceitualmente distintas; correlação={corr:.3f}.",
            )
        )

    return pd.DataFrame(rows)


def build_metric_window_report(bcb: pd.DataFrame, core_metrics: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for short_name, group in bcb.groupby("series_short_name", sort=True):
        group = group.sort_values("date")
        for metric, min_periods in METRIC_MIN_PERIODS.items():
            if metric not in group.columns:
                continue
            values = group[metric]
            valid = group.loc[values.notna(), "date"]
            rows.append(
                {
                    "dataset": "BCB/SGS",
                    "entity": short_name,
                    "metric": metric,
                    "declared_window": "since_2012" if "percentile" in metric else "formula",
                    "min_required_months": min_periods,
                    "available_months": group["date"].nunique(),
                    "non_null_observations": int(values.notna().sum()),
                    "first_valid": valid.min().date() if not valid.empty else None,
                    "last_valid": valid.max().date() if not valid.empty else None,
                    "status": "ok" if values.notna().sum() > 0 and group["date"].nunique() >= min_periods else "insuficiente",
                }
            )
    for key, group in core_metrics.groupby(["core_set_name", "core_name"], sort=True):
        group = group.sort_values("date")
        for metric in ["mom", "rolling_12m", "three_month_saar", "moving_average_3m", "zscore_60m", "percentile_since_2012"]:
            if metric not in group.columns:
                continue
            values = group[metric]
            valid = group.loc[values.notna(), "date"]
            rows.append(
                {
                    "dataset": "Núcleos derivados",
                    "entity": f"{key[0]}:{key[1]}",
                    "metric": metric,
                    "declared_window": "since_2012" if "percentile" in metric else "formula",
                    "min_required_months": METRIC_MIN_PERIODS.get(metric, 1),
                    "available_months": group["date"].nunique(),
                    "non_null_observations": int(values.notna().sum()),
                    "first_valid": valid.min().date() if not valid.empty else None,
                    "last_valid": valid.max().date() if not valid.empty else None,
                    "status": "ok" if values.notna().sum() > 0 and group["date"].nunique() >= METRIC_MIN_PERIODS.get(metric, 1) else "insuficiente",
                }
            )
    return pd.DataFrame(rows)


def _percentile_latest(series: pd.Series, min_periods: int = 24) -> float:
    values = pd.to_numeric(series, errors="coerce").dropna()
    if len(values) < min_periods:
        return float("nan")
    return float(100 * (values <= values.iloc[-1]).mean())


def _snapshot_for_window(bcb: pd.DataFrame, core_metrics: pd.DataFrame, start: pd.Timestamp | None) -> tuple[dict[str, float], int]:
    if start is None:
        bcb_w = bcb.copy()
        core_w = core_metrics.copy()
    else:
        bcb_w = bcb[bcb["date"] >= start].copy()
        core_w = core_metrics[core_metrics["date"] >= start].copy()
    if bcb_w.empty or core_w.empty:
        return {}, 0
    _, metrics = build_metric_snapshot(bcb_w, core_w)
    latest_date = pd.to_datetime(bcb_w["date"]).max()

    diffusion = bcb_w[bcb_w["series_short_name"] == "Difusao"].sort_values("date")
    if not diffusion.empty:
        metrics["diffusion_mm3_percentile"] = _percentile_latest(diffusion["moving_average_3m"])
    ipca = bcb_w[bcb_w["series_short_name"] == "IPCA"].sort_values("date")
    if not ipca.empty and not diffusion.empty:
        ipca_pctl = _percentile_latest(ipca["mom"])
        diffusion_pctl = _percentile_latest(diffusion["moving_average_3m"])
        metrics["localized_shock_score"] = float(ipca_pctl > 80 and diffusion_pctl < 50)

    sample_months = int(pd.to_datetime(bcb_w[bcb_w["date"] <= latest_date]["date"]).nunique())
    return metrics, sample_months


def build_alert_sensitivity_report(
    rules_config: dict[str, Any],
    bcb: pd.DataFrame,
    core_metrics: pd.DataFrame,
) -> pd.DataFrame:
    latest_date = pd.to_datetime(bcb["date"]).max()
    windows = {
        "full_sample": None,
        "since_2020": pd.Timestamp("2020-01-01"),
        "rolling_60m": latest_date - pd.DateOffset(months=59),
    }
    rows: list[dict[str, object]] = []
    for window_name, start in windows.items():
        metrics, sample_months = _snapshot_for_window(bcb, core_metrics, start)
        for rule in rules_config.get("rules", []):
            metric = rule["metric"]
            value = metrics.get(metric, np.nan)
            sufficient = sample_months >= 24 and pd.notna(value)
            triggered = evaluate_condition(value, rule["condition"], rule["threshold"]) if sufficient else False
            rows.append(
                {
                    "alert_id": rule["id"],
                    "metric": metric,
                    "window": window_name,
                    "sample_months": sample_months,
                    "value": value,
                    "condition": rule["condition"],
                    "threshold": rule["threshold"],
                    "triggered": bool(triggered),
                    "window_status": "suficiente" if sufficient else "insuficiente",
                }
            )
    report = pd.DataFrame(rows)
    if report.empty:
        return report
    classifications: dict[str, str] = {}
    for alert_id, group in report.groupby("alert_id"):
        sufficient = group[group["window_status"] == "suficiente"]
        if sufficient.empty:
            classifications[alert_id] = "insuficiente"
        elif sufficient["triggered"].nunique() == 1:
            classifications[alert_id] = "validado"
        else:
            classifications[alert_id] = "sensível à janela"
    report["classification"] = report["alert_id"].map(classifications)
    return report


def _format_counts(df: pd.DataFrame, column: str) -> str:
    if df.empty or column not in df:
        return "sem dados"
    return ", ".join(f"{key}: {value}" for key, value in df[column].value_counts().to_dict().items())


def _df_to_markdown(df: pd.DataFrame, max_rows: int = 20) -> str:
    if df.empty:
        return "_Sem dados._"
    sample = df.head(max_rows).astype(str)
    headers = list(sample.columns)
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for _, row in sample.iterrows():
        lines.append("| " + " | ".join(str(row[col]).replace("\n", " ") for col in headers) + " |")
    if len(df) > max_rows:
        lines.append(f"\n_Exibindo {max_rows} de {len(df)} linhas._")
    return "\n".join(lines)


def build_markdown_report(
    coverage: pd.DataFrame,
    reconciliation: pd.DataFrame,
    metric_windows: pd.DataFrame,
    alert_sensitivity: pd.DataFrame,
    validation_report: pd.DataFrame,
    start_sgs: str,
    start_sidra: str,
) -> str:
    failing_reconciliations = reconciliation[reconciliation["status"].isin(["fail", "warn"])]
    insufficient_metrics = metric_windows[metric_windows["status"] == "insuficiente"]
    sensitive_alerts = alert_sensitivity[alert_sensitivity["classification"] == "sensível à janela"]["alert_id"].drop_duplicates()

    return dedent(f"""# Revisão de Acurácia Econométrica do Dashboard IPCA

## Escopo

Auditoria metodológica e quantitativa do pipeline, usando SGS desde `{start_sgs}` e SIDRA 7060 desde `{start_sidra}`. A auditoria não altera os Parquets consumidos pelo dashboard.

## Cobertura

- Relatório de cobertura: `outputs/audit/coverage_report.csv`.
- Status de janelas métricas: {_format_counts(metric_windows, "status")}.
- Observação: percentis rotulados como `percentile_since_2012` devem ser interpretados pela janela efetiva reportada em `metric_window_report.csv`.

## Reconciliações

Status das reconciliações: {_format_counts(reconciliation, "status")}.

{_df_to_markdown(reconciliation)}

## Alertas

Classificação dos alertas por sensibilidade de janela: {_format_counts(alert_sensitivity.drop_duplicates("alert_id"), "classification")}.

Alertas sensíveis à janela: {", ".join(sensitive_alerts) if not sensitive_alerts.empty else "nenhum"}.

## Validações Existentes

{_df_to_markdown(validation_report)}

## Achados Prioritários

- Reconciliações com atenção: {", ".join(failing_reconciliations["check"]) if not failing_reconciliations.empty else "nenhuma"}.
- Métricas com janela insuficiente: {len(insufficient_metrics)} linhas no relatório de janelas.
- Difusão oficial e difusão calculada por subitem são tratadas como métricas distintas, não como reconciliação de igualdade.

## Recomendações

- Manter o dashboard usando fonte oficial SGS para núcleos, agregados e difusão.
- Usar SIDRA 7060 como referência de decomposição granular e auditar mensalmente a soma de contribuições.
- Renomear futuramente `percentile_since_2012` para refletir a janela efetiva quando a coleta começar após 2012.
- Revisar thresholds de alertas sempre que uma regra for classificada como `sensível à janela`.
""")


def run_audit(start_sgs: str = "2012-01", start_sidra: str = "2020-01", end: str | None = None) -> AuditOutputs:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = AuditOutputs()
    series_config = load_yaml("series_sgs.yaml")
    sidra_config = load_yaml("sidra_7060.yaml")
    core_sets_config = load_yaml("core_sets.yaml")
    alert_rules_config = load_yaml("alert_rules.yaml")

    LOGGER.info("Fetching audit SGS sample from %s", start_sgs)
    bcb_raw = fetch_all_sgs(series_config, start=start_sgs, end=end)
    bcb = transform_bcb_series(bcb_raw)

    LOGGER.info("Fetching audit SIDRA sample from %s", start_sidra)
    sidra_raw = fetch_sidra_7060(sidra_config, start=start_sidra, end=end)
    ipca_items = transform_ipca_items(normalize_sidra_7060(sidra_raw, sidra_config))
    core_metrics = build_core_metrics(bcb, core_sets_config)
    alerts = generate_alerts(alert_rules_config, bcb, core_metrics)
    validation_report = validate_all(bcb, ipca_items, core_sets_config)

    coverage = build_coverage_report(bcb, ipca_items, core_metrics)
    reconciliation = build_reconciliation_report(bcb, ipca_items)
    metric_windows = build_metric_window_report(bcb, core_metrics)
    alert_sensitivity = build_alert_sensitivity_report(alert_rules_config, bcb, core_metrics)

    write_csv(coverage, outputs.coverage)
    write_csv(reconciliation, outputs.reconciliation)
    write_csv(metric_windows, outputs.metric_windows)
    write_csv(alert_sensitivity, outputs.alert_sensitivity)
    outputs.report.write_text(
        build_markdown_report(
            coverage,
            reconciliation,
            metric_windows,
            alert_sensitivity,
            validation_report,
            start_sgs,
            start_sidra,
        ),
        encoding="utf-8",
    )
    LOGGER.info("Audit complete with %s active alert(s).", len(alerts))
    return outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Econometric accuracy audit for the IPCA dashboard.")
    parser.add_argument("--start-sgs", default="2012-01", help="Start month for SGS audit sample.")
    parser.add_argument("--start-sidra", default="2020-01", help="Start month for SIDRA 7060 audit sample.")
    parser.add_argument("--end", default=None, help="Optional end month in YYYY-MM format.")
    parser.add_argument("--log-level", default="INFO", help="Python logging level.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper()), format="%(levelname)s:%(message)s")
    run_audit(start_sgs=args.start_sgs, start_sidra=args.start_sidra, end=args.end)


if __name__ == "__main__":
    main()
