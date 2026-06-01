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
from ipca_dashboard.ai.tools import _num, build_evidence_table, get_headline

pytestmark = pytest.mark.ai_contract


def _bcb() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {
                "date": date,
                "series_short_name": "IPCA",
                "mom": 0.30,
                "rolling_12m": 4.50,
                "moving_average_3m": 0.40,
                "percentile_since_2012": 35.0,
                "moving_average_3m_percentile": 30.0,
            },
            {
                "date": date,
                "series_short_name": "Difusao",
                "mom": 58.0,
                "rolling_12m": None,
                "moving_average_3m": 55.0,
                "percentile_since_2012": 40.0,
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
        [
            {
                "date": date,
                "core_set_name": "bcb_compact",
                "core_name": "Média",
                "mom": 0.40,
                "moving_average_3m": 0.45,
                "is_complete": True,
            }
        ]
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


def test_regime_tool_does_not_mix_months():
    bcb = _bcb()
    bcb.loc[bcb["series_short_name"] == "Difusao", "date"] = pd.Timestamp("2024-02-01")
    table = build_evidence_table(bcb, _items(), _cores(), pd.DataFrame())
    ids = {e.evidence_id for e in table}
    assert "ev_regime" not in ids


# --- Guardrails ------------------------------------------------------------


def test_grounding_rejects_unknown_evidence_id():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [{"text": "algo", "type": "interpretation", "evidence_ids": ["ev_made_up"]}],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_number_claim_allows_multiple_evidence_ids_for_fluent_prose():
    # New contract: a sentence may weave several numbers from several cited
    # evidences. _bcb(): IPCA m/m=0.30, 12m=4.50.
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    good = {
        "claims": [
            {
                "text": "O IPCA avançou 0.30% no mês e acumulou 4.50% em 12 meses.",
                "type": "number",
                "evidence_ids": ["ev_headline_mom", "ev_headline_12m"],
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    validate_ai_output(good, evidence)  # must NOT raise (readable prose)


def test_number_claim_rejects_number_from_uncited_evidence():
    # Anti-hallucination, stricter: the claim cites only ev_headline_mom (0.30)
    # but quotes 4.50, which lives in ev_headline_12m (NOT cited) -> reject.
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [
            {
                "text": "O IPCA acumulou 4.50% em 12 meses.",
                "type": "number",
                "evidence_ids": ["ev_headline_mom"],
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_number_not_in_evidence_is_rejected():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [
            {"text": "O IPCA foi 9.99%", "type": "number", "evidence_ids": ["ev_headline_mom"]}
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_number_claim_rejects_nearby_but_wrong_value():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [
            {
                "text": "IPCA 12m ficou em 4.4%",
                "type": "number",
                "evidence_ids": ["ev_headline_12m"],
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_interpretation_cannot_hide_ungrounded_number():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [
            {
                "text": "A leitura acelerou para 9.99%",
                "type": "interpretation",
                "evidence_ids": ["ev_headline_mom"],
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_short_brief_cannot_hide_ungrounded_number():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [],
        "short_brief": "Resumo: IPCA em 9.99%.",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


@pytest.mark.parametrize(
    "text",
    [
        "O IPCA foi 2026%.",
        "O IPCA acelerou por 9 meses.",
        "O IPCA ficou em 2 anos.",
    ],
)
def test_hidden_numeric_bypasses_are_rejected(text):
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [
            {
                "text": text,
                "type": "number",
                "evidence_ids": ["ev_headline_mom"],
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_regime_claim_rule_id_must_match_regime_evidence():
    evidence = [
        {
            "evidence_id": "ev_regime",
            "metric": "Regime inflacionario",
            "value": "Pressao disseminada",
            "unit": "label",
            "date": "2024-03",
            "source": "OpenIPCA",
            "interpretation": "regime_v1_headline_high_diffusion_high",
        }
    ]
    bad = {
        "claims": [
            {
                "text": "Regime: Pressao disseminada.",
                "type": "regime",
                "evidence_ids": ["ev_regime"],
                "rule_id": "regime_v1_mixed",
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_regime_claim_cannot_hide_ungrounded_number():
    evidence = [
        {
            "evidence_id": "ev_regime",
            "metric": "Regime inflacionario",
            "value": "Pressao disseminada",
            "unit": "label",
            "date": "2024-03",
            "source": "OpenIPCA",
            "interpretation": "regime_v1_headline_high_diffusion_high",
        }
    ]
    bad = {
        "claims": [
            {
                "text": "Regime aponta pressao de 9.99%.",
                "type": "regime",
                "evidence_ids": ["ev_regime"],
                "rule_id": "regime_v1_headline_high_diffusion_high",
            }
        ],
        "short_brief": "x",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_monetary_policy_forecast_is_rejected():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [],
        "short_brief": "O Copom vai cortar a Selic na próxima reunião.",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


@pytest.mark.parametrize(
    "text",
    [
        "O Copom cortara a Selic na proxima reuniao.",
        "O Copom corta a Selic na proxima reuniao.",
        "A Selic sera reduzida na proxima reuniao.",
        "A Selic cai na proxima reuniao.",
        "Compre Tesouro IPCA+ agora.",
        "Eu recomendaria ativos prefixados.",
    ],
)
def test_monetary_policy_and_asset_language_bypasses_are_rejected(text):
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [],
        "short_brief": text,
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    with pytest.raises(GuardrailError):
        validate_ai_output(bad, evidence)


def test_investment_advice_flag_is_rejected():
    evidence = evidence_table_to_dicts(get_headline(_bcb()))
    bad = {
        "claims": [],
        "short_brief": "leitura cautelosa",
        "monetary_policy_tone": "cautious",
        "investment_advice": True,
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


# --- Rounding at the source -----------------------------------------------


def test_num_rounds_to_two_decimals():
    # Evidence values are clean at the source: the model copies 4.39, not the
    # raw float, and a public artifact never shows 4.39171967147336.
    assert _num(4.39171967147336) == 4.39
    assert _num(0.494000000001) == 0.49
    assert _num(65) == 65.0
    assert _num(None) is None
    assert _num(float("nan")) is None


def test_evidence_values_are_rounded():
    table = build_evidence_table(_bcb(), _items(), _cores(), pd.DataFrame())
    for e in table:
        if isinstance(e.value, float):
            assert e.value == round(e.value, 2)


def test_window_words_and_dates_are_not_treated_as_figures():
    # Regression guard: prose like "em 12 meses" / "média de 3 meses" / a
    # reference date must not be read as ungrounded data figures, but a real
    # fake figure must still be caught.
    from ipca_dashboard.ai.guardrails import _numbers_in

    assert _numbers_in("acumulou 4.50% em 12 meses") == [4.5]
    assert _numbers_in("média de 3 meses foi 0.40%") == [0.4]
    assert _numbers_in("em 2024-03 o índice subiu 0.30%") == [0.3]
    assert _numbers_in("em abril de 2026 o índice subiu 0.30%") == [0.3]
    assert _numbers_in("o IPCA foi 2026%") == [2026.0]
    assert _numbers_in("o IPCA acelerou por 9 meses") == [9.0]
    assert _numbers_in("o IPCA ficou em 2 anos") == [2.0]
    assert 9.99 in _numbers_in("o IPCA foi 9.99%")  # fake still caught
