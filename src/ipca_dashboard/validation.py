from __future__ import annotations

import pandas as pd


def validation_row(check: str, status: str, value: float | str, details: str) -> dict[str, object]:
    return {"check": check, "status": status, "value": value, "details": details}


# Minimum set of series whose latest month must match the global latest month.
# Kept small and explicit (spec_V3 §16 keeps v0.1 lean).
CRITICAL_SERIES = [
    "IPCA",
    "Difusao",
    "EX0",
    "EX3",
    "MS",
    "DP",
    "P55",
    "Servicos",
    "Bens_industriais",
    "Administrados",
    "Alimentacao_no_domicilio",
]


def validate_critical_series_freshness(bcb: pd.DataFrame) -> pd.DataFrame:
    """Flag critical series that are stale relative to the global latest month.

    `warn` if any present critical series lags the global max date; `block` if a
    critical series is entirely absent (cannot be evaluated at the latest month).
    """
    if bcb.empty:
        return pd.DataFrame(
            [validation_row("critical_series_freshness", "block", 0, "BCB dataset is empty.")]
        )

    latest = pd.to_datetime(bcb["date"]).max()
    latest_by_series = bcb.groupby("series_short_name")["date"].max()
    present = set(latest_by_series.index)

    missing = [s for s in CRITICAL_SERIES if s not in present]
    stale = [
        s
        for s in CRITICAL_SERIES
        if s in present and pd.to_datetime(latest_by_series[s]) < latest
    ]

    if missing:
        status, value, details = (
            "block",
            ",".join(missing),
            f"Séries críticas ausentes no dataset (latest global {latest:%Y-%m}).",
        )
    elif stale:
        status, value, details = (
            "warn",
            ",".join(stale),
            f"Séries críticas defasadas em relação ao mês mais recente ({latest:%Y-%m}).",
        )
    else:
        status, value, details = (
            "pass",
            0,
            f"Todas as séries críticas estão no mês mais recente ({latest:%Y-%m}).",
        )
    return pd.DataFrame([validation_row("critical_series_freshness", status, value, details)])


def validate_bcb_series(bcb: pd.DataFrame, core_sets_config: dict) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if bcb.empty:
        return pd.DataFrame([validation_row("bcb_not_empty", "block", 0, "BCB dataset is empty.")])

    duplicates = bcb.duplicated(["series_short_name", "date"]).sum()
    rows.append(
        validation_row(
            "bcb_no_duplicate_series_month",
            "pass" if duplicates == 0 else "block",
            int(duplicates),
            "Uma observação por série SGS por mês.",
        )
    )

    latest_by_series = bcb.groupby("series_short_name")["date"].max()
    missing_latest = latest_by_series.isna().sum()
    rows.append(
        validation_row(
            "bcb_latest_dates_present",
            "pass" if missing_latest == 0 else "block",
            int(missing_latest),
            "Toda série SGS configurada tem ao menos uma data.",
        )
    )

    diffusion = bcb[bcb["series_group"] == "diffusion"]
    bad_diffusion = diffusion[~diffusion["mom"].between(0, 100, inclusive="both")]
    rows.append(
        validation_row(
            "diffusion_between_0_and_100",
            "pass" if bad_diffusion.empty else "block",
            int(len(bad_diffusion)),
            "Valores oficiais de difusão devem ficar entre 0 e 100.",
        )
    )

    default_members = (
        core_sets_config.get("core_sets", {}).get("bcb_compact", {}).get("members", [])
    )
    available_cores = set(bcb[bcb["series_group"] == "cores"]["series_short_name"].unique())
    missing_cores = sorted(set(default_members) - available_cores)
    rows.append(
        validation_row(
            "default_core_set_available",
            "pass" if not missing_cores else "block",
            ",".join(missing_cores) if missing_cores else 0,
            "Todos os núcleos do preset default estão presentes na saída SGS.",
        )
    )
    return pd.DataFrame(rows)


def validate_ipca_items(items: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if items.empty:
        return pd.DataFrame([validation_row("ipca_items_not_empty", "block", 0, "Base SIDRA vazia.")])

    duplicates = items.duplicated(["date", "classification_code"]).sum()
    rows.append(
        validation_row(
            "sidra_no_duplicate_item_month",
            "pass" if duplicates == 0 else "block",
            int(duplicates),
            "Uma observação por classificação SIDRA por mês.",
        )
    )

    negative_weights = items[items["weight"].notna() & (items["weight"] < 0)]
    rows.append(
        validation_row(
            "sidra_non_negative_weights",
            "pass" if negative_weights.empty else "block",
            int(len(negative_weights)),
            "Pesos devem ser não negativos.",
        )
    )

    headline = (
        items[items["level"] == "headline"][["date", "mom"]]
        .drop_duplicates("date")
        .set_index("date")["mom"]
    )
    group_sum = items[items["level"] == "group"].groupby("date")["contribution_mom"].sum()
    joined = pd.concat([headline.rename("headline"), group_sum.rename("group_sum")], axis=1).dropna()
    if joined.empty:
        rows.append(
            validation_row(
                "group_contribution_matches_headline",
                "block",
                "missing",
                "Não foi possível comparar a soma de contribuições por grupo com o headline.",
            )
        )
    else:
        joined["abs_diff"] = (joined["headline"] - joined["group_sum"]).abs()
        max_diff = float(joined["abs_diff"].max())
        status = "pass" if max_diff <= 0.02 else "warn" if max_diff <= 0.05 else "block"
        rows.append(
            validation_row(
                "group_contribution_matches_headline",
                status,
                round(max_diff, 4),
                "Diferença absoluta máxima, em p.p., entre soma das contribuições por grupo e headline.",
            )
        )
    return pd.DataFrame(rows)


def validate_all(bcb: pd.DataFrame, items: pd.DataFrame, core_sets_config: dict) -> pd.DataFrame:
    return pd.concat(
        [
            validate_bcb_series(bcb, core_sets_config),
            validate_critical_series_freshness(bcb),
            validate_ipca_items(items),
        ],
        ignore_index=True,
    )


def has_blocking_errors(report: pd.DataFrame) -> bool:
    return bool((report["status"] == "block").any())
