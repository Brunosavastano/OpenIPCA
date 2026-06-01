"""Anthropic provider tests — no network, no real SDK, no key.

Mirror of the OpenAI provider tests: registered by name; resolves to the
deterministic floor without a key/SDK; package import never pulls the SDK; a
fake client's output flows through the existing guardrails (no bypass).
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
from ipca_dashboard.ai.providers.anthropic_provider import _extract_json
from ipca_dashboard.ai.tools import build_evidence_table

pytestmark = pytest.mark.ai_contract


def _bcb() -> pd.DataFrame:
    return pd.DataFrame(
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


def _items() -> pd.DataFrame:
    return pd.DataFrame(
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


def test_anthropic_is_registered_by_name():
    assert "anthropic" in registry.available_providers()


class _BlockVendorImport:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "anthropic" or fullname.startswith("anthropic."):
            raise AssertionError("Anthropic SDK must not be imported in this path")
        if fullname == "openai" or fullname.startswith("openai."):
            raise AssertionError("OpenAI SDK must not be imported in this path")
        return None


def test_resolve_anthropic_without_key_falls_back_to_no_ai(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.modules.pop("anthropic", None)
    monkeypatch.setattr(sys, "meta_path", [_BlockVendorImport(), *sys.meta_path])

    provider = registry.resolve_provider("anthropic")

    assert provider.name == "no_ai"
    assert "anthropic" not in sys.modules  # no SDK import on the fallback path


def test_resolve_anthropic_without_model_falls_back_to_no_ai_without_importing_sdk(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("OPENIPCA_AI_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    sys.modules.pop("anthropic", None)
    monkeypatch.setattr(sys, "meta_path", [_BlockVendorImport(), *sys.meta_path])

    provider = registry.resolve_provider("anthropic")

    assert provider.name == "no_ai"
    assert "anthropic" not in sys.modules


def test_importing_ai_package_does_not_import_vendor_sdks():
    code = """
import importlib.abc
import sys

class BlockVendorImport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"anthropic", "openai"} or fullname.startswith(("anthropic.", "openai.")):
            raise AssertionError("Vendor SDK must not be imported")
        return None

sys.meta_path.insert(0, BlockVendorImport())
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


def test_construction_without_sdk_raises_runtimeerror(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "irrelevant")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")
    from ipca_dashboard.ai.providers.anthropic_provider import AnthropicProvider

    with pytest.raises(RuntimeError):
        AnthropicProvider()


def test_extract_json_tolerates_fence_and_prose():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Aqui está:\n{"a": 1}\nfim') == {"a": 1}
    assert _extract_json('Prosa com {chaves inválidas} antes.\n{"a": 1}\nfim') == {"a": 1}


def test_extract_json_rejects_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        _extract_json('```json\n{"a": }\n```')


def test_fake_anthropic_client_output_passes_guardrails(monkeypatch):
    evidence = evidence_table_to_dicts(
        build_evidence_table(_bcb(), _items(), pd.DataFrame(), pd.DataFrame())
    )
    grounded = {
        "claims": [],
        "short_brief": "Leitura aterrada.",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }

    fake = types.ModuleType("anthropic")

    class _Msg:
        def __init__(self, content):
            # mimic Anthropic content blocks (objects with a .text attr)
            self.content = [types.SimpleNamespace(text=content)]

    class _Client:
        def __init__(self, *a, **k):
            self.messages = types.SimpleNamespace(create=lambda **kw: _Msg(json.dumps(grounded)))

    fake.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    from ipca_dashboard.ai.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False


def test_anthropic_key_is_redacted_from_fallback_error(monkeypatch):
    secret = "redaction-test-anthropic-secret"
    fake = types.ModuleType("anthropic")

    class _Client:
        def __init__(self, *args, **kwargs):
            self.messages = types.SimpleNamespace(
                create=lambda **_kw: (_ for _ in ()).throw(
                    RuntimeError(f"request failed with {kwargs['api_key']}")
                )
            )

    fake.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("OPENIPCA_AI_ENABLED", "true")
    monkeypatch.setenv("OPENIPCA_AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    result = generate_brief(_bcb(), _items(), pd.DataFrame(), pd.DataFrame())

    assert result.provider_name == "no_ai"
    assert result.used_fallback is True
    assert "[redacted]" in (result.error or "")
    serialized = json.dumps(
        {"error": result.error, "trace": result.trace, "metadata": result.metadata},
        ensure_ascii=False,
    )
    assert secret not in serialized
