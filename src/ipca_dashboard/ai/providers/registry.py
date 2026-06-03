"""Provider registry: resolve a provider by name, model-agnostically.

The brief never names a vendor (spec_V3 §3.4: model is config, not code). A
hosted provider registers itself here under a name; resolve_provider() returns
it by config name, falling back to NoAIProvider whenever the requested provider
is unavailable (no key, dependency missing, or unknown name). This is what makes
the AI layer model-upgradable without touching brief.py (§3.5).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable

from ipca_dashboard.ai.providers.base import LLMProvider
from ipca_dashboard.ai.providers.no_ai import NoAIProvider

LOGGER = logging.getLogger(__name__)

# name -> factory returning an LLMProvider (or raising if unavailable).
_REGISTRY: dict[str, Callable[[], LLMProvider]] = {}


def _redact_env_secrets(text: str) -> str:
    redacted = text
    for name, value in os.environ.items():
        if not name.upper().endswith(("API_KEY", "TOKEN", "SECRET")):
            continue
        value = value.strip()
        if len(value) >= 4:
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def register_provider(name: str, factory: Callable[[], LLMProvider]) -> None:
    _REGISTRY[name.lower()] = factory


def resolve_provider(name: str | None) -> LLMProvider:
    """Return the named provider, or NoAIProvider if it can't be built.

    Never raises and never imports a vendor SDK unless that provider's factory
    is actually invoked — so importing this module pulls in no network deps.
    """
    key = (name or "none").lower()
    if key in {"", "none", "no_ai"}:
        return NoAIProvider()
    factory = _REGISTRY.get(key)
    if factory is None:
        LOGGER.warning("AI provider %r is not registered; using the deterministic floor.", key)
        return NoAIProvider()
    try:
        return factory()
    except Exception as exc:  # missing key / SDK / init error -> deterministic floor
        # Keep the deploy diagnostic, but never trust exception text with secrets.
        LOGGER.warning(
            "AI provider %r unavailable (%s: %s); using the deterministic floor.",
            key,
            type(exc).__name__,
            _redact_env_secrets(str(exc)),
        )
        return NoAIProvider()


def available_providers() -> list[str]:
    return ["no_ai", *sorted(_REGISTRY)]
