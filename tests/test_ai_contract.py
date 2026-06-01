"""CP6 AI contract tests — pure, no network. Run: pytest tests/test_ai_contract.py

Covers the Tool API (tool result = evidence), the evidence table, all four
guardrails, and that NoAIProvider always produces a brief that passes them.
"""

import pandas as pd
import pytest

from ipca_dashboard.ai.evidence import Evidence, evidence_table_to_dicts
from ipca_dashboard.ai.guardrails import (
    GuardrailError,
    check_scope,
    validate_ai_output,
)
from ipca_dashboard.ai.providers.no_ai import NoAIProvider
from ipca_dashboard.ai.tools import build_evidence_table, get_headline

pytestmark = pytest.mark.ai_contract


def _bcb() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {
                "date": date, "series_short_name": "IPCA", "mom": 0.30, "rolling_12m": 4.50,
                "moving_average_3m": 0.40, "percentile_since_2012": 35.0,
                "moving_average_3m_percentile": 30.0,
            },
            {
                "date": date, "series_short_name": "Difusao", "mom": 58.0, "rolling_12m": None,
                "moving_average_3m": 55.0, "percentile_since_2012": 40.0,
                "moving_average_3m_percentile": 45.0,
            },
        ]
    )


def _items() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {"date": date, "level": "group", "item_name": "Alimentação", "contribution_mom": 0.18},
            {"date": date, "level": "group", "item_name": "Transportes", "contribution_mom": -0.05},
        ]
    )


def _cores() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [{
            "date": date, "core_set_name": "bcb_compact", "core_name": "Média",
            "mom": 0.40, "moving_average_3m": 0.45, "is_complete": True,
        }]
    )


# --- Tool API / evidence ---------------------------------------------------

def test_tools_return_evidence_with_ids_and_metadata():
    table = get_headline(_bcb())
    assert all(isinstance(e, Evidence) for e in table)
    ids = {e.evidence_id for e in table}
    assert {"ev_headline_mom", "ev_headline_12m", "ev_headline_mm3"} <= ids
    for e in table:
        assert e.source and e.date  # never a bare number


def test_build_evidence_table_includes_regime_and_contributions():
    table = build_evidence_table(_bcb(), _items(), _cores(), pd.DataFrame())
    ids = {e.evidence_id for e in table}
    assert "ev_regime" in ids
    assert any(i.startswith("ev_contrib_top_pos") for i in ids)


# --- Guardrails ------------------------------------------------------------

def test_grounding_rejects_unknown_evidence_id():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [{"text": "algo", "type": "interpretation", "evidence_ids": ["ev_made_up"]}],
        "short_brief": "x", "monetary_policy_tone": "cautious", "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_number_claim_requires_exactly_one_evidence_id():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [{"text": "0.30%", "type": "number", "evidence_ids": ["ev_headline_mom", "ev_headline_12m"]}],
        "short_brief": "x", "monetary_policy_tone": "cautious", "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_number_not_in_evidence_is_rejected():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [{"text": "O IPCA foi 9.99%", "type": "number", "evidence_ids": ["ev_headline_mom"]}],
        "short_brief": "x", "monetary_policy_tone": "cautious", "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_monetary_policy_forecast_is_rejected():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [],
        "short_brief": "O Copom vai cortar a Selic na próxima reunião.",
        "monetary_policy_tone": "cautious", "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_investment_advice_flag_is_rejected():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [], "short_brief": "leitura cautelosa",
        "monetary_policy_tone": "cautious", "investment_advice": True,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_scope_guardrail_refuses_off_topic():
    with pytest.raises(GuardrailError):
        check_scope("Qual a previsão do tempo amanhã?")
    check_scope("Como está a difusão do IPCA?")  # in scope -> no raise


# --- NoAIProvider always passes -------------------------------------------

def test_no_ai_provider_output_passes_guardrails():
    table = build_evidence_table(_bcb(), _items(), _cores(), pd.DataFrame())
    evidence = evidence_table_to_dicts(table)
    provider = NoAIProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False
    assert out["claims"]
