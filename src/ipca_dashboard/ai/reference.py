"""Curated official IPCA reference facts as citable Evidence (spec_V3 §3.8).

These let the grounded Q&A answer methodology/concept questions ("how are the
weights defined?", "IPCA vs INPC?", "when is it released?") while keeping every
claim traceable to an official source — the SAME grounding discipline as the
numeric tools (a claim must still cite an evidence_id, numbers must still come
from a cited value). The corpus is loaded ONLY into the Q&A context, never the
brief (token/quota discipline).

Number rule (the guardrail is NOT relaxed): a fact whose figure the model is
likely to quote puts that figure in `value` (citable); the prose avoids loose
digits. The corpus is owner-reviewed and uses original wording + a source URL —
no verbatim copyrighted text.
"""

from __future__ import annotations

from ipca_dashboard.ai.evidence import Evidence
from ipca_dashboard.config import load_yaml

REFERENCE_YAML = "ipca_reference.yaml"


def load_reference_evidence() -> list[Evidence]:
    """Load the reference corpus as Evidence items. Never raises.

    A missing/malformed file yields an empty list so the Q&A degrades to the
    numeric-only evidence rather than crashing. A fact is skipped unless it has
    an id, a source and an interpretation — a reference must be attributable.
    """
    try:
        raw = load_yaml(REFERENCE_YAML)
    except Exception:  # noqa: BLE001 - missing/invalid corpus must not break the Q&A
        return []
    facts = raw.get("facts", []) if isinstance(raw, dict) else []
    if not isinstance(facts, list):
        return []
    out: list[Evidence] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        fid = fact.get("id")
        source = fact.get("source")
        interpretation = fact.get("interpretation")
        if not fid or not source or not interpretation:
            continue  # a reference fact must be id'd, sourced and described
        value = fact.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float, str)):
            value = None  # bool/list/dict are not valid evidence values
        elif isinstance(value, float) and value != value:  # NaN
            value = None
        out.append(
            Evidence(
                evidence_id=str(fid),
                metric=str(fact.get("metric", fid)),
                value=value,
                unit=str(fact.get("unit", "")),
                date=str(fact.get("date", "")),
                source=str(source),
                interpretation=str(interpretation),
            )
        )
    return out
