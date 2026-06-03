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


def resolve_directives(messages: list[dict], default_system: str) -> tuple[str, str]:
    """Pull the system prompt and the user question out of the message list.

    The caller decides behaviour by task: the brief sends no real system message
    (so the provider's default — a brief writer — is used), while the Q&A sends a
    role='system' message with the analyst prompt. A 'prompt_version=' value is a
    metadata sentinel, not a prompt, so it falls through to the default. role='user'
    carries the question for the Q&A (it is absent for the brief). Centralising this
    keeps every provider consistent and model-agnostic — and was the missing piece
    that made the brief providers silently drop the Q&A question.
    """
    system = default_system
    question = ""
    for message in messages:
        role = message.get("role")
        content = message.get("content")
        if not isinstance(content, str) or not content:
            continue
        if role == "system" and not content.startswith("prompt_version="):
            system = content
        elif role == "user":
            question = content
    return system, question
