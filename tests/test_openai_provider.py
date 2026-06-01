"""OpenAI provider tests — no network, no real SDK, no key.

Verify the drop-in is registered, resolves model-agnostically, and degrades to
the deterministic floor whenever the SDK or key is absent — so CI and the app
never require OpenAI. Also verify a fake client's output still flows through the
existing guardrails (a hosted model cannot bypass grounding).
"""

import sys
import types

import pandas as pd
import pytest

from ipca_dashboard.ai.evidence import evidence_table_to_dicts
from ipca_dashboard.ai.guardrails import validate_ai_output
from ipca_dashboard.ai.providers import registry
from ipca_dashboard.ai.tools import build_evidence_table

pytestmark = pytest.mark.ai_contract


def test_openai_is_registered_by_name():
    assert "openai" in registry.available_providers()


def test_resolve_openai_without_key_falls_back_to_no_ai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = registry.resolve_provider("openai")
    # No key -> factory raises -> registry returns the deterministic floor.
    assert provider.name == "no_ai"


def test_importing_ai_package_does_not_import_openai_sdk():
    # Importing the providers package must not pull in the OpenAI SDK.
    import ipca_dashboard.ai.providers  # noqa: F401

    assert "openai" not in sys.modules or sys.modules.get("openai") is not None
    # The provider module itself must be importable without the SDK present.
    import ipca_dashboard.ai.providers.openai_provider as op  # noqa: F401

    assert hasattr(op, "OpenAIProvider")


def test_provider_construction_without_sdk_raises_runtimeerror(monkeypatch):
    # Simulate the SDK being absent: importing `openai` fails.
    monkeypatch.setitem(sys.modules, "openai", None)
    monkeypatch.setenv("OPENAI_API_KEY", "irrelevant")
    from ipca_dashboard.ai.providers.openai_provider import OpenAIProvider

    with pytest.raises(RuntimeError):
        OpenAIProvider()


def test_fake_openai_client_output_passes_guardrails(monkeypatch):
    """A fake `openai` module lets us exercise generate_structured offline."""
    import json

    bcb = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-03-01"), "series_short_name": "IPCA", "mom": 0.30,
             "rolling_12m": 4.50, "moving_average_3m": 0.40, "percentile_since_2012": 35.0,
             "moving_average_3m_percentile": 30.0},
            {"date": pd.Timestamp("2024-03-01"), "series_short_name": "Difusao", "mom": 58.0,
             "moving_average_3m": 55.0, "percentile_since_2012": 40.0,
             "moving_average_3m_percentile": 45.0},
        ]
    )
    items = pd.DataFrame(
        [
            {"date": pd.Timestamp("2024-03-01"), "level": "group", "item_name": "Alimentação",
             "contribution_mom": 0.18},
            {"date": pd.Timestamp("2024-03-01"), "level": "group", "item_name": "Transportes",
             "contribution_mom": -0.05},
        ]
    )
    evidence = evidence_table_to_dicts(build_evidence_table(bcb, items, pd.DataFrame(), pd.DataFrame()))
    grounded = {
        "claims": [], "short_brief": "Leitura aterrada.",
        "monetary_policy_tone": "cautious", "investment_advice": False,
    }

    # Build a fake `openai` SDK module returning our grounded JSON.
    fake = types.ModuleType("openai")

    class _Resp:
        def __init__(self, content):
            self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]

    class _Client:
        def __init__(self, *a, **k):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **kw: _Resp(json.dumps(grounded))
                )
            )

    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    from ipca_dashboard.ai.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False
