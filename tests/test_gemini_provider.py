"""Gemini provider tests — no network, no real SDK, no key.

Mirror of the OpenAI/Anthropic provider tests: registered by name; resolves to
the deterministic floor without a key/SDK; package import never pulls the SDK; a
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
from ipca_dashboard.ai.providers.gemini_provider import _extract_json
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


def test_gemini_is_registered_by_name():
    assert "gemini" in registry.available_providers()


class _BlockVendorImport:
    def find_spec(self, fullname, path=None, target=None):
        for vendor in ("google.generativeai", "google", "openai", "anthropic"):
            if fullname == vendor or fullname.startswith(vendor + "."):
                # google is a namespace package used elsewhere; only block genai.
                if vendor == "google" and not fullname.startswith("google.generativeai"):
                    continue
                raise AssertionError(f"{fullname} must not be imported in this path")
        return None


def test_resolve_gemini_without_key_falls_back_to_no_ai(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    sys.modules.pop("google.generativeai", None)
    provider = registry.resolve_provider("gemini")
    assert provider.name == "no_ai"
    assert "google.generativeai" not in sys.modules  # no SDK import on the fallback


def test_resolve_gemini_without_model_falls_back_to_no_ai(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("OPENIPCA_AI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    sys.modules.pop("google.generativeai", None)
    provider = registry.resolve_provider("gemini")
    assert provider.name == "no_ai"


def test_importing_ai_package_does_not_import_gemini_sdk():
    code = """
import importlib.abc
import sys

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "google.generativeai" or fullname.startswith("google.generativeai."):
            raise AssertionError("Gemini SDK must not be imported")
        return None

sys.meta_path.insert(0, Block())
import ipca_dashboard.ai
import ipca_dashboard.ai.providers
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_construction_without_sdk_raises_runtimeerror(monkeypatch):
    # Simulate the SDK being absent: importing google.generativeai fails.
    monkeypatch.setitem(sys.modules, "google.generativeai", None)
    monkeypatch.setenv("GOOGLE_API_KEY", "irrelevant")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")
    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(RuntimeError):
        GeminiProvider()


def test_extract_json_tolerates_fence_and_prose():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Resposta:\n{"a": 1}\nfim') == {"a": 1}


def test_extract_json_rejects_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        _extract_json('```json\n{"a": }\n```')


def _fake_genai(returned_text: str, *, capture: dict | None = None) -> types.ModuleType:
    fake = types.ModuleType("google.generativeai")

    class _Resp:
        text = returned_text

    class _Model:
        def __init__(self, model, system_instruction=None):
            if capture is not None:
                capture["model"] = model
                capture["system_instruction"] = system_instruction

        def generate_content(self, prompt, generation_config=None):
            if capture is not None:
                capture["prompt"] = prompt
            return _Resp()

    fake.configure = lambda **kwargs: capture.update(configured=True) if capture is not None else None
    fake.GenerativeModel = _Model
    return fake


def test_fake_gemini_output_passes_guardrails(monkeypatch):
    evidence = evidence_table_to_dicts(
        build_evidence_table(_bcb(), _items(), pd.DataFrame(), pd.DataFrame())
    )
    grounded = {
        "claims": [], "short_brief": "Leitura aterrada.",
        "monetary_policy_tone": "cautious", "investment_advice": False,
    }
    monkeypatch.setitem(sys.modules, "google.generativeai", _fake_genai(json.dumps(grounded)))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False


def test_gemini_key_is_redacted_from_fallback_error(monkeypatch):
    secret = "AIza-redaction-test-secret-value-123456"
    fake = types.ModuleType("google.generativeai")
    fake.configure = lambda **kwargs: None

    class _Model:
        def __init__(self, *a, **k):
            pass

        def generate_content(self, *a, **k):
            raise RuntimeError(f"request failed with key {secret}")

    fake.GenerativeModel = _Model
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)
    monkeypatch.setenv("OPENIPCA_AI_ENABLED", "true")
    monkeypatch.setenv("OPENIPCA_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", secret)
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")

    result = generate_brief(_bcb(), _items(), pd.DataFrame(), pd.DataFrame())

    assert result.provider_name == "no_ai"
    assert result.used_fallback is True
    assert "[redacted]" in (result.error or "")
    serialized = json.dumps(
        {"error": result.error, "trace": result.trace, "metadata": result.metadata},
        ensure_ascii=False,
    )
    assert secret not in serialized
