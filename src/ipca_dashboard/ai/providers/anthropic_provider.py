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
import re

from ipca_dashboard.ai.schemas import BRIEF_SCHEMA

_SYSTEM = (
    "Você é um analista macro. Escreva um brief de inflação do IPCA EM PORTUGUÊS, "
    "em PROSA FLUIDA de research — conecte os números numa narrativa, não faça "
    "frases isoladas nem uma lista telegráfica. "
    "Use SOMENTE os números e fatos da tabela de evidências fornecida. "
    "Uma mesma afirmação pode citar VÁRIAS evidências: ao escrever uma frase com "
    "mais de um número, inclua em evidence_ids TODAS as evidências de TODOS os "
    "números citados naquela frase. NUNCA invente números nem cite um número que "
    "não venha de uma evidência citada na própria frase. "
    "Use no máximo 2 casas decimais. "
    "Escreva para um leitor LEIGO: ao usar um termo técnico inevitável (difusão, "
    "núcleo, MM3M, regime), explique-o em poucas palavras na própria frase. "
    "Para uma afirmação do tipo 'regime', cite a evidência ev_regime e copie em "
    "rule_id o valor do campo interpretation dessa evidência. "
    "NÃO faça previsão de Copom/Selic nem recomende ativos. "
    "Responda APENAS com JSON válido no schema fornecido, sem texto fora do JSON."
)


def _extract_json(text: str) -> dict:
    """Parse the model's text as JSON, tolerating a ```json fence or stray prose."""
    decoder = json.JSONDecoder()
    candidates = [text.strip()]
    candidates.extend(
        match.group(1).strip()
        for match in re.finditer(
            r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL
        )
    )
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        for index, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    raise json.JSONDecodeError("No valid JSON object found", text, 0)


class AnthropicProvider:
    """Generates a grounded brief via the Anthropic Messages API."""

    name = "anthropic"
    capabilities = {"text", "structured"}

    def __init__(self, model: str | None = None, max_tokens: int = 1500) -> None:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set.")
        selected_model = (
            model or os.environ.get("OPENIPCA_AI_MODEL") or os.environ.get("ANTHROPIC_MODEL")
        )
        if not selected_model:
            raise RuntimeError("OPENIPCA_AI_MODEL is not set.")
        # Lazy import: the SDK is only needed when this provider is constructed.
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise RuntimeError(
                "Anthropic provider requires the optional dependency: pip install '.[ai]'"
            ) from exc
        # Model is config, not code.
        self._model = selected_model
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
