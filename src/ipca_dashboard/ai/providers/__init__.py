"""LLM providers for the optional AI layer.

v0.1 minimum: NoAIProvider (always available, no key, deterministic fallback).
A hosted provider (Anthropic/OpenAI, BYOK) is added in CP7. The model is plug-in;
the grounding and guardrails around it are fixed (spec_V3 §3.4/§3.5).
"""

from __future__ import annotations

from ipca_dashboard.ai.providers.base import LLMProvider
from ipca_dashboard.ai.providers.no_ai import NoAIProvider

__all__ = ["LLMProvider", "NoAIProvider"]
