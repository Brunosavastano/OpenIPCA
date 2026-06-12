"""Read the committed AI artifacts for display (spec_V3 §3.8 / §3.6).

The brief is generated once with real tool-use; the trace (tool calls →
evidence_ids → claims) and the audit metadata (model/prompt/evidence hashes)
are committed under ``reports/latest/``. The app renders them as "como a IA
montou este brief" and as the audit stamp under the brief — the proof that the
AI orchestrates deterministic tools instead of narrating free text.

Extracted from the Streamlit app (same pattern as ``staleness.py``) so the
robustness rules are unit-testable: a missing or malformed artifact yields
``None`` and the page simply omits the element, never crashes.
"""

from __future__ import annotations

import json
from pathlib import Path

from ipca_dashboard.ai.evidence import normalize_evidence_ids

MAX_TRACE_BYTES = 2_000_000


def load_trace_summary(path: Path) -> dict | None:
    """Summarize the trace for display: tools called, evidence count, claims.

    Returns ``{"tools": [str], "n_evidence": int, "claims": [{text, evidence_ids}]}``
    or ``None`` when the file is missing, oversized, malformed or empty.
    """
    try:
        if path.stat().st_size > MAX_TRACE_BYTES:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError, RecursionError):
        return None
    if not isinstance(raw, dict):
        return None
    tools = [
        str(call.get("tool"))
        for call in raw.get("tool_calls", []) or []
        if isinstance(call, dict) and call.get("tool")
    ]
    evidence = raw.get("evidence_ids", []) or []
    n_evidence = len(evidence) if isinstance(evidence, list) else 0
    claims = [
        {
            "text": str(claim.get("text", "")),
            "evidence_ids": normalize_evidence_ids(claim.get("evidence_ids")),
        }
        for claim in raw.get("claims", []) or []
        if isinstance(claim, dict) and claim.get("text")
    ]
    if not tools and not claims:
        return None
    return {"tools": tools, "n_evidence": n_evidence, "claims": claims}


def load_brief_metadata(path: Path) -> dict | None:
    """The brief's audit metadata (spec_V3 §3.6), or ``None`` if unusable."""
    try:
        if path.stat().st_size > MAX_TRACE_BYTES:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError, RecursionError):
        return None
    return raw if isinstance(raw, dict) and raw else None


def _short_hash(value: object) -> str:
    """'sha256:c74d958f8534…' -> 'sha256:c74d958f' (readable, still searchable)."""
    text = str(value or "")
    if ":" in text:
        algo, _, digest = text.partition(":")
        return f"{algo}:{digest[:8]}" if digest else ""
    return text[:8]


def brief_stamp_line(meta: dict) -> str:
    """One-line audit stamp from metadata.json — only the fields that exist.

    E.g. "Gerado em 2026-06-04 · provider openai · prompt release_brief_v1
    (sha256:c74d958f) · evidência sha256:7cc3487b". Empty string when nothing
    usable is present (the app then omits the stamp).
    """
    parts: list[str] = []
    generated = str(meta.get("generated_at", ""))[:10]
    if generated:
        parts.append(f"Gerado em {generated}")
    provider = meta.get("provider")
    if provider:
        parts.append(f"provider {provider}")
    prompt_version = meta.get("prompt_version")
    prompt_hash = _short_hash(meta.get("prompt_hash"))
    if prompt_version and prompt_hash:
        parts.append(f"prompt {prompt_version} ({prompt_hash})")
    elif prompt_version:
        parts.append(f"prompt {prompt_version}")
    evidence_hash = _short_hash(meta.get("evidence_hash"))
    if evidence_hash:
        parts.append(f"evidência {evidence_hash}")
    return " · ".join(parts)
