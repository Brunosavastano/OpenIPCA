"""Anthropic provider (optional, BYOK). One drop-in behind the registry.

Mirror of the OpenAI provider for Claude models (Opus / Sonnet / Haiku). The app
stays model-agnostic: nothing imports this module except the registry factory,
and the Anthropic SDK is imported lazily inside the constructor — so importing
the ai package (or running CI) never requires the SDK or a key. The key is read
from the environment and never logged or serialised.

Output is still subject to the same CP6 guardrails, so a hosted model cannot
bypass grounding. Which Claude model is used is config, not code
(ANTHROPIC_MODEL / OPENIPCA_AI_MODEL), so new Claude versions need no code change.
"""

from __future__ import annotations

import json
import os

from ipca_dashboard.ai.schemas import BRIEF_SCHEMA

_SYSTEM = (
    "Você é um analista macro. Escreva um brief de inflação do IPCA EM PORTUGUÊS, "
    "usando SOMENTE os números e fatos da tabela de evidências fornecida. "
    "Cada afirmação deve citar evidence_ids existentes. NUNCA invente números. "
    "NÃO faça previsão de Copom/Selic nem recomende ativos. "
    "Responda APENAS com JSON válido no schema fornecido, sem texto fora do JSON."
)


def _extract_json(text: str) -> dict:
    """Parse the model's text as JSON, tolerating a ```json fence or stray prose."""
    text = text.strip()
    if text.startswith("```"):
        # strip a leading ```json / ``` fence and trailing ```
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


class AnthropicProvider:
    """Generates a grounded brief via the Anthropic Messages API."""

    name = "anthropic"
    capabilities = {"text", "structured"}

    def __init__(self, model: str | None = None, max_tokens: int = 1500) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        # Lazy import: the SDK is only needed when this provider is constructed.
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise RuntimeError(
                "Anthropic provider requires the optional dependency: pip install '.[ai]'"
            ) from exc
        # Model is config, not code: overridable via env, with a sane default.
        self._model = (
            model
            or os.environ.get("OPENIPCA_AI_MODEL")
            or os.environ.get("ANTHROPIC_MODEL")
            or "claude-sonnet-4-6"
        )
        self._max_tokens = max_tokens
        self._client = Anthropic(api_key=api_key)

    def generate_structured(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = 0.0,
    ) -> dict:
        evidence = next((m["content"] for m in messages if m.get("role") == "evidence"), [])
        user = (
            "Tabela de evidências (JSON):\n"
            + json.dumps(evidence, ensure_ascii=False)
            + "\n\nSchema de saída (JSON):\n"
            + json.dumps(schema or BRIEF_SCHEMA, ensure_ascii=False)
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=temperature,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        # Anthropic returns a list of content blocks; concatenate text blocks.
        text = "".join(getattr(block, "text", "") for block in response.content)
        return _extract_json(text)


def _factory() -> AnthropicProvider:
    return AnthropicProvider()
