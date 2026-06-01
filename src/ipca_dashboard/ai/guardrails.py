"""Guardrails: model-independent safety floor for the AI layer (spec_V3 §3.3).

These checks are pure and never change when the model changes. A failure raises
GuardrailError; callers (CP7) catch it and fall back to the deterministic brief,
so the AI can never block the product.

Enforced:
- grounding: every claim cites existing evidence_id(s); a "number" claim cites
  exactly one; "interpretation" one or more; "regime" needs a rule_id.
- numbers: the output introduces no number absent from the evidence values.
- monetary policy: tone is from a constrained set; no Copom/Selic forecast or
  asset recommendation; investment_advice must be False.
- scope: a question/topic outside Brazilian inflation is refused.
"""

from __future__ import annotations

import re

from ipca_dashboard.ai.schemas import CLAIM_TYPES, MONETARY_POLICY_TONES

# Out-of-scope: monetary-policy forecasting and investment advice.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\bcomprar?\b", re.IGNORECASE),
    re.compile(r"\bvende[r]?\b", re.IGNORECASE),
    re.compile(r"\bcopom\s+(vai|deve|ir[aá])\b", re.IGNORECASE),
    re.compile(r"\bselic\s+(vai|deve|ir[aá]|cair[aá]?|sub[ií])", re.IGNORECASE),
    re.compile(r"\b(corte|alta)\s+de\s+juros\s+(certo|garantid)", re.IGNORECASE),
    re.compile(r"\brecomend[ao]\b", re.IGNORECASE),
    re.compile(r"\b(compre|venda)\s+(a[çc][õo]es|ativos|d[óo]lar)", re.IGNORECASE),
]

_IN_SCOPE_HINTS = [
    "ipca", "inflação", "inflacao", "núcleo", "nucleo", "difusão", "difusao",
    "preço", "preco", "headline", "regime", "contribuição", "contribuicao",
]

# A claimed figure: a number NOT immediately followed by a letter. This skips
# label tokens like "12m", "3m", "MM3M" (months/window names), which are not
# figures the model is asserting.
_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?(?![A-Za-z0-9])")


class GuardrailError(ValueError):
    """Raised when AI output violates a guardrail."""


def _numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUMBER_RE.findall(text or ""):
        try:
            out.append(float(m.replace(",", ".")))
        except ValueError:
            continue
    return out


def _matches(claimed: float, value: float) -> bool:
    # Match if equal at the evidence's natural precision (<= 2 decimals).
    return any(round(claimed, p) == round(value, p) for p in (0, 1, 2))


def check_scope(question: str) -> None:
    """Refuse a question that is not about Brazilian inflation."""
    text = (question or "").lower()
    if not any(hint in text for hint in _IN_SCOPE_HINTS):
        raise GuardrailError("Out of scope: question is not about Brazilian inflation.")


def check_monetary_policy(output: dict) -> None:
    tone = output.get("monetary_policy_tone")
    if tone is not None and tone not in MONETARY_POLICY_TONES:
        raise GuardrailError(f"Invalid monetary_policy_tone: {tone!r}")
    if output.get("investment_advice", False):
        raise GuardrailError("investment_advice must be False.")
    blob = " ".join(
        [output.get("short_brief", "")] + [c.get("text", "") for c in output.get("claims", [])]
    )
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(blob):
            raise GuardrailError(f"Forbidden monetary-policy/investment language: /{pat.pattern}/")


def check_grounding(output: dict, evidence: list[dict]) -> None:
    by_id = {ev["evidence_id"]: ev for ev in evidence}
    for claim in output.get("claims", []):
        ctype = claim.get("type")
        ids = claim.get("evidence_ids", []) or []
        if ctype not in CLAIM_TYPES:
            raise GuardrailError(f"Unknown claim type: {ctype!r}")
        unknown = [i for i in ids if i not in by_id]
        if unknown:
            raise GuardrailError(f"Claim cites unknown evidence_id(s): {unknown}")
        if ctype == "number":
            if len(ids) != 1:
                raise GuardrailError("A 'number' claim must cite exactly one evidence_id.")
            cited_value = by_id[ids[0]].get("value")
            for claimed in _numbers_in(claim.get("text", "")):
                if not isinstance(cited_value, (int, float)) or cited_value != cited_value:
                    raise GuardrailError("A 'number' claim cites evidence with no numeric value.")
                if not _matches(claimed, float(cited_value)):
                    raise GuardrailError(
                        f"Number {claimed} does not match cited evidence value {cited_value}."
                    )
        elif ctype == "interpretation":
            if len(ids) < 1:
                raise GuardrailError("An 'interpretation' claim needs >= 1 evidence_id.")
        elif ctype == "regime":
            if not claim.get("rule_id"):
                raise GuardrailError("A 'regime' claim must reference a rule_id.")
            if len(ids) < 1:
                raise GuardrailError("A 'regime' claim needs >= 1 evidence_id.")


def validate_ai_output(output: dict, evidence: list[dict]) -> None:
    """Run all guardrails; raise GuardrailError on the first violation."""
    check_grounding(output, evidence)
    check_monetary_policy(output)
