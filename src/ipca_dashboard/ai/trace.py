"""Read the persisted orchestration trace for display (spec_V3 §3.8).

The brief is generated once with real tool-use and the trace (tool calls →
evidence_ids → claims) is committed to ``reports/latest/ai_trace.json``. The app
renders it as "como a IA montou este brief" — the proof that the AI orchestrates
deterministic tools instead of narrating free text.

Extracted from the Streamlit app (same pattern as ``staleness.py``) so the
robustness rules are unit-testable: a missing or malformed trace yields ``None``
and the page simply omits the expander, never crashes.
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
