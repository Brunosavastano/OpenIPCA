"""LLM providers for the optional AI layer.

v0.1 minimum: NoAIProvider (always available, no key, deterministic fallback).
A hosted provider (BYOK, registered by name) is added in CP7. The model is plug-in;
the grounding and guardrails around it are fixed (spec_V3 §3.4/§3.5).
"""

from __future__ import annotations

from ipca_dashboard.ai.providers.base import LLMProvider
from ipca_dashboard.ai.providers.no_ai import NoAIProvider
from ipca_dashboard.ai.providers.registry import register_provider


def _make_openai() -> LLMProvider:
    # Imported lazily so the OpenAI SDK is never required to load this package
    # or run CI — only when the 'openai' provider is actually resolved.
    from ipca_dashboard.ai.providers.openai_provider import OpenAIProvider

    return OpenAIProvider()


def _make_anthropic() -> LLMProvider:
    # Imported lazily so the Anthropic SDK is never required to load this package
    # or run CI — only when the 'anthropic' provider is actually resolved.
    from ipca_dashboard.ai.providers.anthropic_provider import AnthropicProvider

    return AnthropicProvider()


def _make_gemini() -> LLMProvider:
    # Imported lazily so the Google SDK is never required to load this package
    # or run CI — only when the 'gemini' provider is actually resolved.
    from ipca_dashboard.ai.providers.gemini_provider import GeminiProvider

    return GeminiProvider()


# Register hosted providers by name. The factory runs only on resolve_provider(),
# so no vendor SDK is imported at package-load time (model-agnostic).
register_provider("openai", _make_openai)
register_provider("anthropic", _make_anthropic)
register_provider("gemini", _make_gemini)

__all__ = ["LLMProvider", "NoAIProvider"]
