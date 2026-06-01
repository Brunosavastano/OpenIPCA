"""Provider protocol: the thin, model-agnostic seam (spec_V3 §3.4).

Kept deliberately small for v0.1. capabilities lets the app gate features by
tier (no-ai / local / frontier) without hard-coding model assumptions.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    capabilities: set[str]  # subset of {"text", "structured", "tools", "reasoning"}

    def generate_structured(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = 0.0,
    ) -> dict:
        """Return a structured object conforming to `schema`."""
        ...
