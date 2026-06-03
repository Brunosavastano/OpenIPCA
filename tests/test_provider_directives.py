"""The Q&A question must reach the model, and the caller's system prompt must win.

Regression guard for the analyst rewrite: the brief providers (OpenAI/Anthropic)
used to extract only the evidence and silently DROP the user question, so the
Q&A model never saw what was asked. These tests pin, per provider, that the
question is sent and that a role='system' prompt from the caller overrides the
provider's default brief prompt.
"""

import json
import sys
import types

import pytest

from ipca_dashboard.ai.providers.base import resolve_directives

pytestmark = pytest.mark.ai_contract

SYS = "ANALISTA_MARK"
Q = "PERGUNTA_MARK guerra do Irã"
_GROUNDED = {"answer": "ok", "claims": [], "monetary_policy_tone": "cautious", "investment_advice": False}


def _qa_messages():
    return [
        {"role": "system", "content": SYS},
        {"role": "user", "content": Q},
        {"role": "evidence", "content": [{"evidence_id": "ev_x", "value": 1.0}]},
    ]


# --- the helper in isolation ------------------------------------------------

def test_resolve_uses_default_for_version_sentinel():
    msgs = [{"role": "system", "content": "prompt_version=ask_ipca_v2"}, {"role": "evidence", "content": []}]
    system, question = resolve_directives(msgs, "DEFAULT")
    assert system == "DEFAULT"  # sentinel is metadata, not a prompt
    assert question == ""


def test_resolve_overrides_system_and_extracts_question():
    system, question = resolve_directives(_qa_messages(), "DEFAULT")
    assert system == SYS
    assert question == Q


def test_resolve_brief_has_no_question():
    msgs = [{"role": "evidence", "content": []}]
    system, question = resolve_directives(msgs, "DEFAULT")
    assert system == "DEFAULT"
    assert question == ""


def test_resolve_ignores_non_string_content():
    msgs = [{"role": "user", "content": None}, {"role": "system", "content": 123}]
    system, question = resolve_directives(msgs, "DEFAULT")
    assert system == "DEFAULT"
    assert question == ""


# --- OpenAI sends the question and the caller's system ----------------------

def test_openai_sends_question_and_system(monkeypatch):
    captured = {}
    fake = types.ModuleType("openai")

    class _Resp:
        def __init__(self, content):
            self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=content))]

    def _create(**kw):
        captured.update(kw)
        return _Resp(json.dumps(_GROUNDED))

    class _Client:
        def __init__(self, *a, **k):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=_create))

    fake.OpenAI = _Client
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    from ipca_dashboard.ai.providers.openai_provider import OpenAIProvider

    OpenAIProvider().generate_structured(_qa_messages(), schema={}, temperature=0.0)
    msgs = captured["messages"]
    assert msgs[0]["content"] == SYS  # caller's analyst prompt, not the brief default
    assert Q in msgs[1]["content"]  # the question reached the model


# --- Anthropic sends the question and the caller's system -------------------

def test_anthropic_sends_question_and_system(monkeypatch):
    captured = {}
    fake = types.ModuleType("anthropic")

    class _Client:
        def __init__(self, *a, **k):
            self.messages = types.SimpleNamespace(create=self._create)

        def _create(self, **kw):
            captured.update(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(text=json.dumps(_GROUNDED))])

    fake.Anthropic = _Client
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    from ipca_dashboard.ai.providers.anthropic_provider import AnthropicProvider

    AnthropicProvider().generate_structured(_qa_messages(), schema={}, temperature=0.0)
    assert captured["system"] == SYS
    assert Q in captured["messages"][0]["content"]


# --- Gemini sends the question and the caller's system ----------------------

def test_gemini_sends_question_and_system(monkeypatch):
    captured = {}
    fake = types.ModuleType("google.generativeai")

    class _Resp:
        text = json.dumps(_GROUNDED)

    class _Model:
        def __init__(self, model, system_instruction=None):
            captured["system_instruction"] = system_instruction

        def generate_content(self, prompt, generation_config=None):
            captured["prompt"] = prompt
            return _Resp()

    fake.configure = lambda **kw: None
    fake.GenerativeModel = _Model
    monkeypatch.setitem(sys.modules, "google.generativeai", fake)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("OPENIPCA_AI_MODEL", "test-model")

    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    GeminiProvider().generate_structured(_qa_messages(), schema={}, temperature=0.0)
    assert captured["system_instruction"] == SYS  # built per call with the analyst prompt
    assert Q in captured["prompt"]
