"""Gemini provider tests — no network, no SDK, no key.

The provider talks to the Gemini `generateContent` REST endpoint with `requests`
(NOT the google-generativeai SDK). These tests mock `requests.post`, so they
never touch the network: registered by name; resolves to the deterministic floor
without a key/model; the SDK is never imported; a fake REST response flows
through the existing guardrails (no bypass); the key travels in a header (never
the URL) and is redacted on error.
"""

import json
import logging
import subprocess
import sys

import pandas as pd
import pytest
import requests

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


# --- REST mocks (a stand-in for requests.post / requests.Response) -----------


def _gemini_payload(text: str) -> dict:
    """The minimal generateContent success envelope: one candidate, one text part."""
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class _FakeResponse:
    """Just enough of a requests.Response for the provider: raise_for_status + json."""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def _capture_post(captured: dict, returned_text: str):
    def _post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["body"] = json  # the request body, not the json module
        return _FakeResponse(_gemini_payload(returned_text))

    return _post


class _StatusResponse:
    """A response whose raise_for_status raises requests.HTTPError for >= 400."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} error")
            err.response = self  # type: ignore[assignment]
            raise err

    def json(self) -> dict:
        return self._payload


# --- registration / fallback ------------------------------------------------


def test_gemini_is_registered_by_name():
    assert "gemini" in registry.available_providers()


def test_resolve_gemini_without_key_falls_back_to_no_ai(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    provider = registry.resolve_provider("gemini")
    assert provider.name == "no_ai"  # no key -> deterministic floor, no network


def test_resolve_gemini_without_model_falls_back_to_no_ai(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.delenv("OPENIPCA_AI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    provider = registry.resolve_provider("gemini")
    assert provider.name == "no_ai"


def test_provider_resolution_log_redacts_google_api_key(monkeypatch, caplog):
    secret = "redaction-test-google-secret"

    def _factory():
        raise RuntimeError(f"constructed error with key {secret}")

    registry.register_provider("leaky_gemini_test", _factory)
    monkeypatch.setenv("GOOGLE_API_KEY", secret)

    with caplog.at_level(logging.WARNING):
        provider = registry.resolve_provider("leaky_gemini_test")

    assert provider.name == "no_ai"
    assert secret not in caplog.text
    assert "[redacted]" in caplog.text


def test_importing_ai_package_does_not_import_gemini_sdk():
    # The REST provider must never pull the heavy SDK, even transitively.
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
import ipca_dashboard.ai.providers.gemini_provider
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


# --- construction guards ----------------------------------------------------


def test_construction_without_key_raises_runtimeerror(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")
    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(RuntimeError):
        GeminiProvider()


def test_construction_without_model_raises_runtimeerror(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "irrelevant")
    monkeypatch.delenv("OPENIPCA_AI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(RuntimeError):
        GeminiProvider()


# --- tolerant JSON extraction -----------------------------------------------


def test_extract_json_tolerates_fence_and_prose():
    assert _extract_json('{"a": 1}') == {"a": 1}
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('Resposta:\n{"a": 1}\nfim') == {"a": 1}


def test_extract_json_rejects_invalid_json():
    with pytest.raises(json.JSONDecodeError):
        _extract_json('```json\n{"a": }\n```')


# --- a fake REST response flows through the guardrails ----------------------


def test_fake_gemini_output_passes_guardrails(monkeypatch):
    evidence = evidence_table_to_dicts(
        build_evidence_table(_bcb(), _items(), pd.DataFrame(), pd.DataFrame())
    )
    grounded = {
        "claims": [],
        "short_brief": "Leitura aterrada.",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }
    captured = {}
    monkeypatch.setattr(
        "ipca_dashboard.ai.providers.gemini_provider.requests.post",
        _capture_post(captured, json.dumps(grounded)),
    )
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    provider = GeminiProvider()
    out = provider.generate_structured(
        [{"role": "evidence", "content": evidence}], schema={}, temperature=0.0
    )
    validate_ai_output(out, evidence)  # must not raise
    assert out["investment_advice"] is False
    # the key travels in the header, never in the URL; the model picks the endpoint.
    assert "test-key" not in captured["url"]
    assert captured["headers"].get("x-goog-api-key") == "test-key"
    assert "gemini-2.0-flash" in captured["url"]


@pytest.mark.parametrize(
    "bad_output",
    [
        {
            "claims": [],
            "short_brief": "Leitura com número inventado de 9,99%.",
            "monetary_policy_tone": "cautious",
            "investment_advice": False,
        },
        {
            "claims": [],
            "short_brief": "O Copom deve cortar a Selic.",
            "monetary_policy_tone": "cautious",
            "investment_advice": False,
        },
    ],
)
def test_fake_gemini_output_still_goes_through_cp6_guardrails(monkeypatch, bad_output):
    monkeypatch.setattr(
        "ipca_dashboard.ai.providers.gemini_provider.requests.post",
        _capture_post({}, json.dumps(bad_output)),
    )
    monkeypatch.setenv("OPENIPCA_AI_ENABLED", "true")
    monkeypatch.setenv("OPENIPCA_AI_PROVIDER", "gemini")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")

    result = generate_brief(_bcb(), _items(), pd.DataFrame(), pd.DataFrame())

    assert result.used_fallback is True
    assert result.provider_name == "no_ai"


def test_no_candidates_raises_runtimeerror(monkeypatch):
    # A safety block returns promptFeedback with no candidates -> surface why.
    def _post(url, headers=None, json=None, timeout=None):
        return _FakeResponse({"promptFeedback": {"blockReason": "SAFETY"}})

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _post)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-2.0-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(RuntimeError):
        GeminiProvider().generate_structured(
            [{"role": "evidence", "content": []}], schema={}, temperature=0.0
        )


def test_gemini_key_is_redacted_from_fallback_error(monkeypatch):
    secret = "redaction-test-secret-value"

    def _boom(url, headers=None, json=None, timeout=None):
        raise RuntimeError(f"request failed with key {secret}")

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _boom)
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


# --- resilience: transient errors retry + fall back to a stable model --------


def test_recovers_via_fallback_on_a_transient_error(monkeypatch):
    calls = {"n": 0}
    seen_urls: list[str] = []
    seen_timeouts: list[int] = []

    def _post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        seen_urls.append(url)
        seen_timeouts.append(timeout)
        if calls["n"] == 1:
            return _StatusResponse(503)  # primary blips (overload)
        return _FakeResponse(_gemini_payload('{"answer": "ok", "claims": []}'))

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _post)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-3.5-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    out = GeminiProvider().generate_structured(
        [{"role": "evidence", "content": []}], schema={}, temperature=0.0
    )
    assert out == {"answer": "ok", "claims": []}
    assert calls["n"] == 2  # primary failed -> the next model in the chain answered
    assert all("test-key" not in url for url in seen_urls)  # key stays in the header
    assert seen_timeouts == [20, 20]  # short per-call timeout, not the old 60s


def test_falls_back_to_a_stable_model_when_the_primary_keeps_failing(monkeypatch):
    seen: list[str] = []

    def _post(url, headers=None, json=None, timeout=None):
        seen.append(url)
        if "gemini-3.5-flash" in url:
            return _StatusResponse(503)  # primary model overloaded
        return _FakeResponse(_gemini_payload('{"answer": "via fallback", "claims": []}'))

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _post)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-3.5-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    out = GeminiProvider().generate_structured(
        [{"role": "evidence", "content": []}], schema={}, temperature=0.0
    )
    assert out["answer"] == "via fallback"
    assert any("gemini-2.5-flash" in u for u in seen)  # it fell back to a stable model
    assert sum("gemini-3.5-flash" in u for u in seen) == 1  # primary tried once, then moved on
    # the configured model is still PRIMARY (tried first), not replaced
    assert "gemini-3.5-flash" in seen[0]


@pytest.mark.parametrize("status_code", [400, 403])
def test_a_non_transient_error_is_not_retried_or_fallen_back(monkeypatch, status_code):
    calls = {"n": 0}

    def _post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return _StatusResponse(status_code)  # bad request/key -> retrying won't help

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _post)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-3.5-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(requests.HTTPError):
        GeminiProvider().generate_structured(
            [{"role": "evidence", "content": []}], schema={}, temperature=0.0
        )
    assert calls["n"] == 1  # no retry, no fallback


def test_parse_error_is_not_retried_or_fallen_back(monkeypatch):
    calls = {"n": 0}

    def _post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return _FakeResponse(_gemini_payload("not json"))

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _post)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-3.5-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(json.JSONDecodeError):
        GeminiProvider().generate_structured(
            [{"role": "evidence", "content": []}], schema={}, temperature=0.0
        )
    assert calls["n"] == 1  # parser/schema failures are real errors, not transient


def test_all_models_transient_failing_exhausts_then_raises(monkeypatch):
    # Every model overloaded -> the chain exhausts and the last error propagates,
    # so CP7 degrades to the deterministic fallback (never a crash).
    calls = {"n": 0}
    statuses = iter([503, 502, 504, 500, 429])

    def _post(url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        return _StatusResponse(next(statuses))

    monkeypatch.setattr("ipca_dashboard.ai.providers.gemini_provider.requests.post", _post)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "gemini-3.5-flash")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    with pytest.raises(requests.HTTPError) as excinfo:
        GeminiProvider().generate_structured(
            [{"role": "evidence", "content": []}], schema={}, temperature=0.0
        )
    assert calls["n"] == 5  # configured primary + two fallback models over two passes
    assert excinfo.value.response.status_code == 429  # last transient error propagates
