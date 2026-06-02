"""Streamlit render smoke tests.

AppTest renders pages, not just imports the app. This catches runtime-only UI
errors such as nested expanders when reports/latest artifacts are present.
"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def _ensure_processed_fixtures() -> list[Path]:
    """Create minimal processed parquet files when CI checkout has no data artifacts."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    created = []
    paths = {
        "bcb": PROCESSED / "bcb_series_monthly.parquet",
        "items": PROCESSED / "ipca_items_monthly.parquet",
        "cores": PROCESSED / "core_metrics_monthly.parquet",
        "alerts": PROCESSED / "alerts.parquet",
    }
    if all(path.exists() for path in paths.values()):
        return created

    dates = pd.to_datetime(["2024-02-01", "2024-03-01"])
    bcb = pd.DataFrame(
        [
            {
                "date": date,
                "series_short_name": series,
                "mom": mom,
                "rolling_12m": rolling,
                "moving_average_3m": mm3,
                "percentile_since_2012": pctl,
                "moving_average_3m_percentile": mm3_pctl,
            }
            for date in dates
            for series, mom, rolling, mm3, pctl, mm3_pctl in [
                ("IPCA", 0.4, 4.2, 0.35, 55.0, 50.0),
                ("Difusao", 58.0, None, 57.0, 60.0, 62.0),
            ]
        ]
    )
    item_rows = []
    for date in dates:
        item_rows.extend(
            [
                {
                    "date": date,
                    "level": "headline",
                    "classification_code": "0",
                    "parent_classification_code": "",
                    "item_name": "IPCA",
                    "contribution_mom": 0.30,
                    "weight": 100.0,
                    "mom": 0.30,
                    "group_classification_code": "",
                },
                {
                    "date": date,
                    "level": "group",
                    "classification_code": "1",
                    "parent_classification_code": "",
                    "item_name": "Alimentação e bebidas",
                    "contribution_mom": 0.20,
                    "weight": 20.0,
                    "mom": 1.0,
                    "group_classification_code": "1",
                },
                {
                    "date": date,
                    "level": "group",
                    "classification_code": "2",
                    "parent_classification_code": "",
                    "item_name": "Transportes",
                    "contribution_mom": 0.10,
                    "weight": 18.0,
                    "mom": 0.5,
                    "group_classification_code": "2",
                },
                {
                    "date": date,
                    "level": "subgroup",
                    "classification_code": "11",
                    "parent_classification_code": "1",
                    "item_name": "Alimentação no domicílio",
                    "contribution_mom": 0.15,
                    "weight": 12.0,
                    "mom": 0.8,
                    "group_classification_code": "1",
                },
                {
                    "date": date,
                    "level": "item",
                    "classification_code": "1101",
                    "parent_classification_code": "11",
                    "item_name": "Cereais",
                    "contribution_mom": 0.08,
                    "weight": 3.0,
                    "mom": 0.7,
                    "group_classification_code": "1",
                },
                {
                    "date": date,
                    "level": "subitem",
                    "classification_code": "1101001",
                    "parent_classification_code": "1101",
                    "item_name": "Arroz",
                    "contribution_mom": 0.04,
                    "weight": 1.0,
                    "mom": 0.6,
                    "group_classification_code": "1",
                },
            ]
        )
    items = pd.DataFrame(item_rows)
    core_rows = []
    for date in dates:
        for name, mom in [
            ("EX0", 0.30),
            ("EX3", 0.35),
            ("DP", 0.40),
            ("MS", 0.45),
            ("P55", 0.50),
            ("Média", 0.40),
        ]:
            core_rows.append(
                {
                    "date": date,
                    "core_set_name": "bcb_compact",
                    "core_name": name,
                    "mom": mom,
                    "moving_average_3m": mom + 0.05,
                    "rolling_12m": 4.0 + mom,
                    "three_month_saar": 5.0 + mom,
                    "is_complete": True,
                }
            )
    cores = pd.DataFrame(core_rows)
    alerts = pd.DataFrame(
        columns=["reference_month", "alert_id", "severity", "metric", "value", "message"]
    )

    for path, frame in [
        (paths["bcb"], bcb),
        (paths["items"], items),
        (paths["cores"], cores),
        (paths["alerts"], alerts),
    ]:
        if not path.exists():
            frame.to_parquet(path, index=False)
            created.append(path)
    return created


def test_streamlit_app_renders_all_pages():
    created = _ensure_processed_fixtures()
    try:
        app = AppTest.from_file("dashboard/app.py")
        app.run(timeout=60)
        assert not app.exception

        pages = list(app.sidebar.radio[0].options)
        assert pages == ["Painel executivo", "Decomposição", "Núcleos", "Difusão", "Alertas", "Metodologia"]

        for page in pages:
            app.sidebar.radio[0].set_value(page)
            app.run(timeout=60)
            assert not app.exception, f"Streamlit page failed to render: {page}"
    finally:
        for path in created:
            path.unlink(missing_ok=True)
