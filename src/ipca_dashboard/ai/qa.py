"""Live, grounded "Ask the IPCA" Q&A (spec_V3 §3.8 — pulled forward from v0.2).

answer_question() is the brief's pattern applied to a user question: build the
evidence table (reused), ask the configured provider for a grounded ANSWER, and
validate it with the CP6 guardrails. It NEVER raises and NEVER lets the AI block
the product:

- input guardrails first (check_question = injection + scope): an injection or
  off-topic question is refused WITHOUT calling the model.
- on any model/guardrail failure -> a graceful fallback (no crash).

It is model-agnostic (talks only to the LLMProvider Protocol) and the key is
never logged (errors run through _redact_secrets, reused from brief.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ipca_dashboard.ai import SCHEMA_VERSION
from ipca_dashboard.ai.brief import _hash, _provider_name, _redact_secrets
from ipca_dashboard.ai.config import load_ai_config
from ipca_dashboard.ai.evidence import evidence_table_to_dicts
from ipca_dashboard.ai.guardrails import (
    GuardrailError,
    check_grounding,
    check_monetary_policy,
    check_question,
)
from ipca_dashboard.ai.providers.base import LLMProvider
from ipca_dashboard.ai.providers.registry import resolve_provider
from ipca_dashboard.ai.schemas import ANSWER_SCHEMA
from ipca_dashboard.ai.tools import build_evidence_table

QA_PROMPT_VERSION = "ask_ipca_v1"
REFUSAL_TEXT = (
    "Só consigo responder perguntas sobre a inflação brasileira (IPCA) com base "
    "nos dados oficiais já calculados. Reformule sua pergunta sobre o IPCA — por "
    "exemplo: o que puxou a inflação do mês, se está espalhada, ou como estão os núcleos."
)


@dataclass
class QAResult:
    answer: str
    claims: list[dict]
    evidence: list[dict]
    trace: dict
    metadata: dict
    mode: str  # "ai" | "deterministic" | "fallback" | "refused"
    provider_name: str
    refused: bool = False
    error: str | None = field(default=None)


def _messages(question: str, evidence: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": f"prompt_version={QA_PROMPT_VERSION}"},
        {"role": "user", "content": question},
        {"role": "evidence", "content": evidence},
    ]


def _refused_result(question: str, reason: str) -> QAResult:
    return QAResult(
        answer=REFUSAL_TEXT,
        claims=[],
        evidence=[],
        trace={"prompt_version": QA_PROMPT_VERSION, "refused": True},
        metadata={"mode": "refused", "schema_version": SCHEMA_VERSION},
        mode="refused",
        provider_name="none",
        refused=True,
        error=reason,
    )


def _fallback_answer() -> dict:
    return {
        "answer": (
            "Não consegui consultar a IA agora. Use o painel e o brief para ver os "
            "números oficiais do mês — eles continuam disponíveis e auditáveis."
        ),
        "claims": [],
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }


def _require_answer_payload(out: object) -> dict:
    if not isinstance(out, dict):
        raise GuardrailError("Answer output must be a JSON object.")
    answer = out.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise GuardrailError("Answer output is missing a non-empty answer.")
    claims = out.get("claims")
    if claims is None:
        out["claims"] = []
    elif not isinstance(claims, list):
        raise GuardrailError("Answer output claims must be a list.")
    return out


def answer_question(
    question: str,
    bcb: pd.DataFrame,
    ipca_items: pd.DataFrame,
    core_metrics: pd.DataFrame,
    alerts: pd.DataFrame,
    *,
    provider: LLMProvider | None = None,
    core_set: str = "bcb_compact",
) -> QAResult:
    """Answer a user question, grounded in the evidence. Never raises."""
    try:
        question_text = "" if question is None else str(question)
    except Exception:  # noqa: BLE001 - hostile input must not crash the Q&A box
        question_text = ""

    # 1) Input guardrails — refuse injection / off-scope BEFORE calling the model.
    try:
        check_question(question_text)
    except GuardrailError as exc:
        return _refused_result(
            question_text, _redact_secrets(f"{type(exc).__name__}: {exc}")
        )

    # 2) Resolve provider (config) + build evidence (reused from the brief path).
    used_fallback = False
    error: str | None = None
    try:
        config = load_ai_config()
        if provider is None:
            provider = resolve_provider(config.provider if config.is_active else "none")
        evidence = evidence_table_to_dicts(
            build_evidence_table(bcb, ipca_items, core_metrics, alerts, core_set)
        )
    except Exception as exc:  # noqa: BLE001 - AI must never block
        from ipca_dashboard.ai.providers.no_ai import NoAIProvider

        provider, evidence, used_fallback = NoAIProvider(), [], True
        error = _redact_secrets(f"{type(exc).__name__}: {exc}")

    messages = _messages(question_text, evidence)

    # 3) Generate + validate (grounding + monetary policy). Any failure -> fallback.
    try:
        out = provider.generate_structured(messages, ANSWER_SCHEMA, temperature=0.0)
        out = _require_answer_payload(out)
        check_grounding(out, evidence)
        check_monetary_policy(out)
    except (GuardrailError, Exception) as exc:  # noqa: BLE001 - AI must never block
        used_fallback = True
        error = error or _redact_secrets(f"{type(exc).__name__}: {exc}")
        out = _fallback_answer()

    final_provider = _provider_name(provider)
    mode = "fallback" if used_fallback else ("deterministic" if final_provider == "no_ai" else "ai")
    claims = out.get("claims", []) or []
    trace = {
        "prompt_version": QA_PROMPT_VERSION,
        "question": question_text,
        "evidence_ids": [e["evidence_id"] for e in evidence],
        "claims": [
            {"text": c.get("text"), "type": c.get("type"), "evidence_ids": c.get("evidence_ids", [])}
            for c in claims
        ],
        "used_fallback": used_fallback,
    }
    metadata = {
        "provider": final_provider,
        "mode": mode,
        "prompt_version": QA_PROMPT_VERSION,
        "question_hash": _hash(question_text),
        "evidence_hash": _hash(evidence),
        "schema_version": SCHEMA_VERSION,
        "used_fallback": used_fallback,
    }
    return QAResult(
        answer=out.get("answer", ""),
        claims=claims,
        evidence=evidence,
        trace=trace,
        metadata=metadata,
        mode=mode,
        provider_name=final_provider,
        refused=False,
        error=error,
    )
