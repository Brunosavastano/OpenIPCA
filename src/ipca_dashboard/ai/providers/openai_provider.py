"""OpenAI provider (optional, BYOK). One drop-in behind the registry.

The app stays model-agnostic: nothing imports this module except the registry
factory, and the OpenAI SDK is imported lazily inside the factory — so importing
the ai package (or running CI) never requires the SDK or a key. The key is read
from the environment and never logged or serialised.

This provider only *produces* a structured brief; it is still subject to the
same CP6 guardrails as any output, so a hosted model cannot bypass grounding.
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
    "Responda APENAS com JSON no schema fornecido."
)


class OpenAIProvider:
    """Generates a grounded brief via the OpenAI Chat Completions API."""

    name = "openai"
    capabilities = {"text", "structured"}

    def __init__(self, model: str | None = None) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        # Lazy import: the SDK is only needed when this provider is constructed.
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise RuntimeError(
                "OpenAI provider requires the optional dependency: pip install '.[ai]'"
            ) from exc
        # Model is config, not code: overridable via env, with a sane default.
        self._model = model or os.environ.get("OPENIPCA_AI_MODEL", "gpt-4o-mini")
        self._client = OpenAI(api_key=api_key)

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
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        )
        return json.loads(response.choices[0].message.content)


def _factory() -> OpenAIProvider:
    return OpenAIProvider()
