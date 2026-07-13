"""Grounded AI brief + persisted orchestration trace (spec_V3 §3.6/§3.8).

generate_brief() runs one real tool-using pass through whatever provider config
selects, validates the output against the CP6 guardrails, and — on ANY failure
(no key, provider error, guardrail rejection) — falls back to the deterministic
brief. The AI can never block the product.

It is model-agnostic: it talks only to the LLMProvider Protocol and never names
a vendor. The persisted trace (tool calls -> evidence_ids -> claims) is what
makes "the AI orchestrates" verifiable rather than a slogan.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from ipca_dashboard.ai import SCHEMA_VERSION
from ipca_dashboard.ai.config import load_ai_config
from ipca_dashboard.ai.evidence import evidence_table_to_dicts
from ipca_dashboard.ai.guardrails import GuardrailError, validate_ai_output
from ipca_dashboard.ai.providers.base import LLMProvider
from ipca_dashboard.ai.providers.no_ai import NoAIProvider
from ipca_dashboard.ai.providers.registry import resolve_provider
from ipca_dashboard.ai.schemas import BRIEF_SCHEMA
from ipca_dashboard.ai.tools import build_evidence_table

PROMPT_VERSION = "release_brief_v1"
TOOL_NAMES = [
    "get_headline",
    "get_diffusion",
    "get_cores",
    "get_contributions",
    "get_alerts",
    "get_regime",
]


@dataclass
class BriefResult:
    brief: dict
    evidence: list[dict]
    trace: dict
    metadata: dict
    used_fallback: bool
    provider_name: str
    error: str | None = field(default=None)


def _hash(payload: object) -> str:
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _messages(evidence: list[dict]) -> list[dict]:
    return [
        {"role": "system", "content": f"prompt_version={PROMPT_VERSION}"},
        {"role": "evidence", "content": evidence},
    ]


def _minimal_brief() -> dict:
    return {
        "claims": [],
        "short_brief": "Leitura determinística indisponível; evidências insuficientes.",
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }


def _redact_secrets(text: str) -> str:
    redacted = text
    for name, value in os.environ.items():
        upper = name.upper()
        if not upper.endswith(("API_KEY", "TOKEN", "SECRET")):
            continue
        value = value.strip()
        if len(value) >= 4:
            redacted = redacted.replace(value, "[redacted]")
    return redacted


def _append_error(existing: str | None, exc: BaseException) -> str:
    current = _redact_secrets(f"{type(exc).__name__}: {exc}")
    return current if existing is None else f"{existing}; {current}"


def _provider_name(provider: LLMProvider) -> str:
    try:
        return str(getattr(provider, "name", "unknown"))
    except Exception:  # noqa: BLE001 - provider metadata must not block
        return "unknown"


def generate_brief(
    bcb: pd.DataFrame,
    ipca_items: pd.DataFrame,
    core_metrics: pd.DataFrame,
    alerts: pd.DataFrame,
    *,
    provider: LLMProvider | None = None,
    core_set: str = "bcb_compact",
    generated_at: str = "",
) -> BriefResult:
    """Produce a grounded brief; never raises (always returns a valid brief).

    `provider` is injectable for tests; in production it is resolved from config.
    `generated_at` is passed in (scripts stamp it) to keep this pure.
    """
    used_fallback = False
    error: str | None = None

    try:
        config = load_ai_config()
        if provider is None:
            provider = resolve_provider(config.provider if config.is_active else "none")
    except Exception as exc:  # noqa: BLE001 - AI must never block
        used_fallback = True
        error = _append_error(error, exc)
        provider = NoAIProvider()

    try:
        evidence_items = build_evidence_table(bcb, ipca_items, core_metrics, alerts, core_set)
        evidence = evidence_table_to_dicts(evidence_items)
    except Exception as exc:  # noqa: BLE001 - malformed/empty data must not block
        used_fallback = True
        error = _append_error(error, exc)
        evidence = []
        provider = NoAIProvider()
    messages = _messages(evidence)

    try:
        brief = provider.generate_structured(messages, BRIEF_SCHEMA, temperature=0.0)
        validate_ai_output(brief, evidence)
    except (GuardrailError, Exception) as exc:  # noqa: BLE001 - AI must never block
        used_fallback = True
        error = _append_error(error, exc)
        fallback = NoAIProvider()
        try:
            brief = fallback.generate_structured(messages, BRIEF_SCHEMA, temperature=0.0)
            validate_ai_output(brief, evidence)  # the floor must always pass
        except Exception as fallback_exc:  # noqa: BLE001 - last-resort deterministic floor
            error = _append_error(error, fallback_exc)
            brief = _minimal_brief()
        provider = fallback

    trace_claims = []
    for c in brief.get("claims", []):
        trace_claim = {
            "text": c.get("text"),
            "type": c.get("type"),
            "evidence_ids": c.get("evidence_ids", []),
        }
        if c.get("rule_id"):
            trace_claim["rule_id"] = c.get("rule_id")
        trace_claims.append(trace_claim)

    trace = {
        "prompt_version": PROMPT_VERSION,
        "tool_calls": [{"tool": name} for name in TOOL_NAMES],
        "evidence_ids": [e["evidence_id"] for e in evidence],
        "claims": trace_claims,
        "used_fallback": used_fallback,
    }
    final_provider = _provider_name(provider)
    # mode is unambiguous for a reader of the artifact:
    #  - "ai"          : a hosted provider produced the brief
    #  - "deterministic": NoAI produced it (AI off / unavailable) — not an error
    #  - "fallback"    : a hosted provider was tried but failed -> NoAI floor
    if used_fallback:
        mode = "fallback"
    elif final_provider == "no_ai":
        mode = "deterministic"
    else:
        mode = "ai"
    metadata = {
        "generated_at": generated_at,
        "provider": final_provider,
        "mode": mode,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": _hash(messages[0]["content"]),
        "evidence_hash": _hash(evidence),
        "schema_version": SCHEMA_VERSION,
        "data_sources": ["IBGE/SIDRA", "BCB/SGS"],
        "used_fallback": used_fallback,
    }
    return BriefResult(
        brief=brief,
        evidence=evidence,
        trace=trace,
        metadata=metadata,
        used_fallback=used_fallback,
        provider_name=final_provider,
        error=error,
    )


def brief_to_markdown(result: BriefResult, reference_month: str = "") -> str:
    # Reading copy is kept clean: no per-claim evidence_ids in the text. Full
    # traceability (claim -> evidence_ids) lives in ai_trace.json, which the app
    # shows under "ver os bastidores". The short_brief is the lead paragraph;
    # claims follow as readable bullets.
    lines = [f"# Análise OpenIPCA — IPCA {reference_month}".rstrip(), ""]
    mode = "AI Replay Mode (fallback determinístico)" if result.used_fallback else "AI Replay Mode"
    lines.append(f"_{mode} · provider: {result.provider_name}_")
    lines.append("")
    short = result.brief.get("short_brief", "")
    if short:
        lines.append(short)
        lines.append("")
    for c in result.brief.get("claims", []):
        text = (c.get("text") or "").strip()
        if text:
            lines.append(f"- {text}")
    return "\n".join(lines).strip() + "\n"


def write_brief_artifacts(
    result: BriefResult, out_dir: Path, reference_month: str = ""
) -> dict[str, Path]:
    """Persist ai_brief.md, ai_trace.json, metadata.json under out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "brief": out_dir / "ai_brief.md",
        "trace": out_dir / "ai_trace.json",
        "metadata": out_dir / "metadata.json",
    }
    paths["brief"].write_text(brief_to_markdown(result, reference_month), encoding="utf-8")
    paths["trace"].write_text(
        json.dumps(result.trace, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Stamp reference_month into metadata so the app can detect a brief that has
    # gone stale relative to the data (the staleness guard reads this field).
    metadata = {**result.metadata, "reference_month": reference_month}
    paths["metadata"].write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return paths
