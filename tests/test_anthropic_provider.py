"""Anthropic provider tests — no network, no real SDK, no key.

Mirror of the OpenAI provider tests: registered by name; resolves to the
deterministic floor without a key/SDK; package import never pulls the SDK; a
fake client's output flows through the existing guardrails (no bypass).
"""

import json
import sys
import types

import pandas as pd
import pytest

from ipca_dashboard.ai.evidence import evidence_table_to_dicts
from ipca_dashboard.ai.guardrails import validate_ai_output
from ipca_dashboard.ai.providers import registry
from ipca_dashboard.ai.providers.anthropic_provider import _extract_json
from ipca_dashboard.ai.tools import build_evidence_table

pytestmark = pytest.mark.ai_contract


def _bcb() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-03-01"), "series_short_name": "IPCA", "mom": 0.30,
             "rolling_12m": 4.50, "moving_average_3m": 0.40, "percentile_since_2012": 35.0,
             "moving_average_3m_percentile": 30.0},
            {"date": pd.Timestamp("2024-03-01"), "series_short_name": "Difusao", "mom": 58.0,
             "moving_average_3m": 55.0, "percentile_since_2012": 40.0,
             "moving_average_3m_percentile": 45.0},
        ]
    )


def _items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-03-01"), "level": "group", "item_name": "Alimentação",
             "contribution_mom": 0.18},
            {"date": pd.Timestamp("2024-03-01"), "level": "group", "item_name": "Transportes",
             "contribution_mom": -0.05},
        ]
    )


def test_anthropic_is_registered_by_name():
    assert "anthropic" in registry.available_providers()


def test_resolve_anthropic_without_key_falls_back_to_no_ai(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.modules.pop("anthropic", None)
    provider = registry.resolve_provider("anthropic")
    assert provider.name == "no_ai"
    assert "anthropic" not in sys.modules  # no SDK import on the fallback path


def test_construction_without_sdk_raises_runtimeerror(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "irrelevant")
    from ipca_dashboard.ai.providers.anthropic_provider import AnthropicProvider

    with pytest.raises(RuntimeError):
        AnthropicProvider()


def test_extract_json_tolerates_fence_and_prose():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Aqui está:\n{"a": 1}\nfim') == {"a": 1}


def test_fake_anthropic_client_output_passes_guardrails(monkeypatch):
    evidence = evidence_table_to_dicts(build_evidence_table(_bcb(), _items(), pd.DataFrame(), pd.DataFrame()))
    grounded = {
        "claims": [], "short_brief": "Leitura aterrada.",
        "monetary_policy_tone": "cautious", "investment_advice": False,
    }

    fake = types.ModuleType("anthropic")

    class _Msg:
        def __init__(self, content):
            # mimic Anthropic content blocks (objects with a .text attr)
            self.content = [types.SimpleNamespace(text=content)]

    class _Client:
        def __init__(self, *a, **k):
            self.messages = types.SimpleNamespace(
                create=lambda **kw: _Msg(json.dumps(grounded))
            )

    fake.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from ipca_dashboard.ai.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False
