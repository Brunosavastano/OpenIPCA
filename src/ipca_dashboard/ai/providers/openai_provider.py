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
    "Responda APENAS com JSON no schema fornecido."
)


def _is_temperature_rejection(exc: Exception) -> bool:
    message = str(exc).lower()
    if "temperature" not in message:
        return False
    rejection_markers = (
        "unsupported",
        "does not support",
        "not support",
        "invalid",
        "not allowed",
        "only accept",
        "only support",
    )
    return any(marker in message for marker in rejection_markers)


class OpenAIProvider:
    """Generates a grounded brief via the OpenAI Chat Completions API."""

    name = "openai"
    capabilities = {"text", "structured"}

    def __init__(self, model: str | None = None) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        selected_model = (
            model or os.environ.get("OPENIPCA_AI_MODEL") or os.environ.get("OPENAI_MODEL")
        )
        if not selected_model:
            raise RuntimeError("OPENIPCA_AI_MODEL is not set.")
        # Lazy import: the SDK is only needed when this provider is constructed.
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without SDK
            raise RuntimeError(
                "OpenAI provider requires the optional dependency: pip install '.[ai]'"
            ) from exc
        # Model is config, not code.
        self._model = selected_model
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
        kwargs = {
            "model": self._model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": user},
            ],
        }
        try:
            response = self._client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            # Some newer models only accept the default temperature (1). Retry
            # once without the param so any such model works (model-agnostic),
            # instead of falling back to the deterministic brief.
            if _is_temperature_rejection(exc):
                kwargs.pop("temperature", None)
                response = self._client.chat.completions.create(**kwargs)
            else:
                raise
        return json.loads(response.choices[0].message.content)


def _factory() -> OpenAIProvider:
    return OpenAIProvider()
