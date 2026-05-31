import pandas as pd

from ipca_dashboard.diagnostics import build_regime_context, classify_latest_regime
from ipca_dashboard.regime import classify_inflation_regime


def _ctx(headline, diffusion):
    return {"headline_percentile": headline, "diffusion_mm3_percentile": diffusion}


def test_broad_disinflation_low_low():
    r = classify_inflation_regime(_ctx(30.0, 40.0))
    assert r.regime == "broad_disinflation"
    assert r.rule_id == "regime_v1_headline_low_diffusion_low"


def test_fragile_disinflation_low_headline_high_diffusion():
    r = classify_inflation_regime(_ctx(30.0, 85.0))
    assert r.regime == "fragile_disinflation"


def test_localized_shock_high_headline_low_diffusion():
    r = classify_inflation_regime(_ctx(90.0, 30.0))
    assert r.regime == "localized_shock"


def test_broad_pressure_high_high():
    r = classify_inflation_regime(_ctx(90.0, 90.0))
    assert r.regime == "broad_pressure"


def test_mixed_when_between_thresholds():
    r = classify_inflation_regime(_ctx(65.0, 65.0))
    assert r.regime == "mixed"


def test_insufficient_data_when_missing():
    assert classify_inflation_regime(_ctx(None, 50.0)).regime == "insufficient_data"
    assert classify_inflation_regime(_ctx(50.0, float("nan"))).regime == "insufficient_data"
    assert classify_inflation_regime({}).regime == "insufficient_data"


def test_deterministic_same_input_same_output():
    a = classify_inflation_regime(_ctx(90.0, 90.0))
    b = classify_inflation_regime(_ctx(90.0, 90.0))
    assert a.regime == b.regime and a.rule_id == b.rule_id


def test_evidence_ids_pass_through():
    r = classify_inflation_regime(
        {"headline_percentile": 90.0, "diffusion_mm3_percentile": 90.0, "evidence_ids": ["ev_a", "ev_b"]}
    )
    assert r.evidence_ids == ("ev_a", "ev_b")


def test_build_regime_context_reads_existing_columns():
    date = pd.Timestamp("2024-03-01")
    bcb = pd.DataFrame(
        [
            {"date": date, "series_short_name": "IPCA", "percentile_since_2012": 90.0,
             "moving_average_3m_percentile": 10.0},
            {"date": date, "series_short_name": "Difusao", "percentile_since_2012": 10.0,
             "moving_average_3m_percentile": 85.0},
        ]
    )
    ctx = build_regime_context(bcb)
    assert ctx["headline_percentile"] == 90.0
    assert ctx["diffusion_mm3_percentile"] == 85.0
    # Headline high + diffusion high -> broad_pressure.
    assert classify_latest_regime(bcb).regime == "broad_pressure"
