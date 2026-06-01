"""Structured output schema for the AI brief (spec_V3 §3.3).

A claim is {text, type, evidence_ids[]}, where type is one of:
- "number"        -> exactly ONE evidence_id (a figure must trace to one fact)
- "interpretation"-> one OR MORE evidence_ids
- "regime"        -> one rule_id (in rule_id) + one or more evidence_ids

monetary_policy_tone is constrained; investment_advice must be False.
"""

from __future__ import annotations

CLAIM_TYPES = {"number", "interpretation", "regime"}
MONETARY_POLICY_TONES = {"cautious", "benign", "adverse", "mixed"}

# Conceptual JSON schema (used for prompting / documentation in CP7).
BRIEF_SCHEMA: dict = {
    "type": "object",
    "required": ["claims", "short_brief", "monetary_policy_tone", "investment_advice"],
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["text", "type", "evidence_ids"],
                "properties": {
                    "text": {"type": "string"},
                    "type": {"enum": sorted(CLAIM_TYPES)},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "rule_id": {"type": "string"},
                },
            },
        },
        "short_brief": {"type": "string"},
        "monetary_policy_tone": {"enum": sorted(MONETARY_POLICY_TONES)},
        "investment_advice": {"const": False},
    },
}
