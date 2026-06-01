"""OpenAI provider tests — no network, no real SDK, no key.

Verify the drop-in is registered, resolves model-agnostically, and degrades to
the deterministic floor whenever the SDK or key is absent — so CI and the app
never require OpenAI. Also verify a fake client's output still flows through the
existing guardrails (a hosted model cannot bypass grounding).
"""

import json
import subprocess
import sys
import types

import pandas as pd
import pytest

from ipca_dashboard.ai.brief import generate_brief
from ipca_dashboard.ai.evidence import evidence_table_to_dicts
from ipca_dashboard.ai.guardrails import validate_ai_output
from ipca_dashboard.ai.providers import registry
from ipca_dashboard.ai.tools import build_evidence_table

pytestmark = pytest.mark.ai_contract


def test_openai_is_registered_by_name():
    assert "openai" in registry.available_providers()


class _BlockOpenAIImport:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "openai" or fullname.startswith("openai."):
            raise AssertionError("OpenAI SDK must not be imported in this path")
        return None


def test_resolve_openai_without_key_falls_back_to_no_ai_without_importing_sdk(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sys.modules.pop("openai", None)
    monkeypatch.setattr(sys, "meta_path", [_BlockOpenAIImport(), *sys.meta_path])

    provider = registry.resolve_provider("openai")

    # No key -> factory raises -> registry returns the deterministic floor.
    assert provider.name == "no_ai"
    assert "openai" not in sys.modules


def test_resolve_openai_without_model_falls_back_to_no_ai_without_importing_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENIPCA_AI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    sys.modules.pop("openai", None)
    monkeypatch.setattr(sys, "meta_path", [_BlockOpenAIImport(), *sys.meta_path])

    provider = registry.resolve_provider("openai")

    assert provider.name == "no_ai"
    assert "openai" not in sys.modules


def test_importing_ai_package_does_not_import_openai_sdk():
    code = """
import importlib.abc
import sys

class BlockOpenAIImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "openai" or fullname.startswith("openai."):
            raise AssertionError("OpenAI SDK must not be imported")
        return None

sys.meta_path.insert(0, BlockOpenAIImport())
import ipca_dashboard.ai
import ipca_dashboard.ai.providers
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_provider_construction_without_sdk_raises_runtimeerror(monkeypatch):
    # Simulate the SDK being absent: importing `openai` fails.
    monkeypatch.setitem(sys.modules, "openai", None)
    monkeypatch.setenv("OPENAI_API_KEY", "irrelevant")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")
    from ipca_dashboard.ai.providers.openai_provider import OpenAIProvider

    with pytest.raises(RuntimeError):
        OpenAIProvider()


def test_fake_openai_client_output_passes_guardrails(monkeypatch):
    """A fake `openai` module lets us exercise generate_structured offline."""
    bcb = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-03-01"),
                "series_short_name": "IPCA",
                "mom": 0.30,
                "rolling_12m": 4.50,
                "moving_average_3m": 0.40,
                "percentile_since_2012": 35.0,
                "moving_average_3m_percentile": 30.0,
            },
            {
                "date": pd.Timestamp("2024-03-01"),
                "series_short_name": "Difusao",
                "mom": 58.0,
                "moving_average_3m": 55.0,
                "percentile_since_2012": 40.0,
                "moving_average_3m_percentile": 45.0,
            },
        ]
    )
    items = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-03-01"),
                "level": "group",
                "item_name": "Alimentação",
                "contribution_mom": 0.18,
            },
            {
                "date": pd.Timestamp("2024-03-01"),
                "level": "group",
                "item_name": "Transportes",
                "contribution_mom": -0.05,
            },
        ]
    )
    evidence = evidence_table_to_dicts(
        build_evidence_table(bcb, items, pd.DataFrame(), pd.DataFrame())
    )
    grounded = {
        "claims": [],
        "short_brief": "Leitura aterrada.",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }

    # Build a fake `openai` SDK module returning our grounded JSON.
    fake = types.ModuleType("openai")

    class _Resp:
        def __init__(self, content):
            self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]

    class _Client:
        def __init__(self, *a, **k):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(create=lambda **kw: _Resp(json.dumps(grounded)))
            )

    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    from ipca_dashboard.ai.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False


def test_provider_key_is_redacted_from_fallback_error(monkeypatch):
    secret = "redaction-test-secret-value"
    fake = types.ModuleType("openai")

    class _Client:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **_kw: (_ for _ in ()).throw(
                        RuntimeError(f"request failed with {kwargs['api_key']}")
                    )
                )
            )

    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENIPCA_AI_ENABLED", "true")
    monkeypatch.setenv("OPENIPCA_AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    bcb = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-03-01"),
                "series_short_name": "IPCA",
                "mom": 0.30,
                "rolling_12m": 4.50,
                "moving_average_3m": 0.40,
                "percentile_since_2012": 35.0,
                "moving_average_3m_percentile": 30.0,
            },
            {
                "date": pd.Timestamp("2024-03-01"),
                "series_short_name": "Difusao",
                "mom": 58.0,
                "moving_average_3m": 55.0,
                "percentile_since_2012": 40.0,
                "moving_average_3m_percentile": 45.0,
            },
        ]
    )
    items = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-03-01"),
                "level": "group",
                "item_name": "Alimentação",
                "contribution_mom": 0.18,
            }
        ]
    )

    result = generate_brief(bcb, items, pd.DataFrame(), pd.DataFrame())

    assert result.provider_name == "no_ai"
    assert result.used_fallback is True
    assert "[redacted]" in (result.error or "")
    serialized = json.dumps(
        {"error": result.error, "trace": result.trace, "metadata": result.metadata},
        ensure_ascii=False,
    )
    assert secret not in serialized
