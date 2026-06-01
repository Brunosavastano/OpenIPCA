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
import unicodedata

from ipca_dashboard.ai.schemas import CLAIM_TYPES, MONETARY_POLICY_TONES

# Out-of-scope: monetary-policy forecasting and investment advice. Patterns are
# matched against accent-stripped lowercase text.
_FORBIDDEN_PATTERNS = [
    re.compile(
        r"\bcopom\b.{0,40}\b"
        r"(vai|deve|ira|corta|cortara|cortar|reduz|reduzira|reduzir|"
        r"baixa|baixara|baixar|sobe|subira|subir|eleva|elevara|elevar|"
        r"aumenta|aumentara|aumentar|mantem|mantera|manter)\b"
    ),
    re.compile(
        r"\bselic\b.{0,40}\b"
        r"(vai|deve|ira|sera|cai|caira|cair|cortada|reduzida|sobe|subira|subir|"
        r"elevada|aumentada|mantida|fica|ficara)\b"
    ),
    re.compile(
        r"\b(corte|alta|queda|manutencao)\s+(da\s+selic|de\s+juros)\s+"
        r"(certo|garantid|inevitavel)\w*\b"
    ),
    re.compile(
        r"\b(compre|compra|comprar|venda|vender)\b.{0,40}\b"
        r"(acao|acoes|ativo|ativos|dolar|tesouro|ipca\+|ntn-?b|bova11|ivvb11|"
        r"fundo|fundos|titulo|titulos)\b"
    ),
    re.compile(
        r"\b(recomendo|recomenda|recomendar|recomendaria|sugiro|indico)\b.{0,40}\b"
        r"(acao|acoes|ativo|ativos|dolar|tesouro|ipca\+|ntn-?b|selic|fundo|fundos|"
        r"titulo|titulos)\b"
    ),
]

_IN_SCOPE_HINTS = [
    "ipca",
    "inflacao",
    "nucleo",
    "difusao",
    "preco",
    "headline",
    "regime",
    "contribuicao",
]

# A claimed figure: a number not attached to letters or a date/range hyphen.
# This skips labels like "12m", "3m", "MM3M", "p80", and dates like "2024-03".
_NUMBER_RE = re.compile(r"(?<![A-Za-z-])-?\d+(?:[.,]\d+)?(?![A-Za-z0-9-])")


class GuardrailError(ValueError):
    """Raised when AI output violates a guardrail."""


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _numbers_in(text: str) -> list[float]:
    out: list[float] = []
    for m in _NUMBER_RE.findall(text or ""):
        try:
            out.append(float(m.replace(",", ".")))
        except ValueError:
            continue
    return out


def _matches(claimed: float, value: float) -> bool:
    # Evidence values are displayed at up to two decimals; allow formatting noise only.
    return abs(claimed - value) <= 0.005


def _numeric_evidence_values(evidence: list[dict]) -> list[float]:
    values: list[float] = []
    for ev in evidence:
        value = ev.get("value")
        if isinstance(value, (int, float)) and value == value:
            values.append(float(value))
    return values


def _require_numbers_in_evidence(text: str, values: list[float]) -> None:
    for claimed in _numbers_in(text):
        if not any(_matches(claimed, value) for value in values):
            raise GuardrailError(f"Number {claimed} is not grounded in evidence.")


def check_scope(question: str) -> None:
    """Refuse a question that is not about Brazilian inflation."""
    text = _normalize_text(question or "")
    if not any(hint in text for hint in _IN_SCOPE_HINTS):
        raise GuardrailError("Out of scope: question is not about Brazilian inflation.")


def check_monetary_policy(output: dict) -> None:
    tone = output.get("monetary_policy_tone")
    if tone is not None and tone not in MONETARY_POLICY_TONES:
        raise GuardrailError(f"Invalid monetary_policy_tone: {tone!r}")
    if output.get("investment_advice", False):
        raise GuardrailError("investment_advice must be False.")
    blob = _normalize_text(
        " ".join(
            [output.get("short_brief", "")] + [c.get("text", "") for c in output.get("claims", [])]
        )
    )
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(blob):
            raise GuardrailError(f"Forbidden monetary-policy/investment language: /{pat.pattern}/")


def check_grounding(output: dict, evidence: list[dict]) -> None:
    by_id = {ev["evidence_id"]: ev for ev in evidence}
    numeric_values = _numeric_evidence_values(evidence)
    for claim in output.get("claims", []):
        ctype = claim.get("type")
        ids = claim.get("evidence_ids", []) or []
        text = claim.get("text", "")
        if ctype not in CLAIM_TYPES:
            raise GuardrailError(f"Unknown claim type: {ctype!r}")
        unknown = [i for i in ids if i not in by_id]
        if unknown:
            raise GuardrailError(f"Claim cites unknown evidence_id(s): {unknown}")
        if ctype == "number":
            if len(ids) != 1:
                raise GuardrailError("A 'number' claim must cite exactly one evidence_id.")
            cited_value = by_id[ids[0]].get("value")
            for claimed in _numbers_in(text):
                if not isinstance(cited_value, (int, float)) or cited_value != cited_value:
                    raise GuardrailError("A 'number' claim cites evidence with no numeric value.")
                if not _matches(claimed, float(cited_value)):
                    raise GuardrailError(
                        f"Number {claimed} does not match cited evidence value {cited_value}."
                    )
        elif ctype == "interpretation":
            if len(ids) < 1:
                raise GuardrailError("An 'interpretation' claim needs >= 1 evidence_id.")
            _require_numbers_in_evidence(text, numeric_values)
        elif ctype == "regime":
            if not claim.get("rule_id"):
                raise GuardrailError("A 'regime' claim must reference a rule_id.")
            if len(ids) < 1:
                raise GuardrailError("A 'regime' claim needs >= 1 evidence_id.")
            if "ev_regime" in ids and claim.get("rule_id") != by_id["ev_regime"].get(
                "interpretation"
            ):
                raise GuardrailError("A 'regime' claim rule_id does not match ev_regime.")
            _require_numbers_in_evidence(text, numeric_values)
    _require_numbers_in_evidence(output.get("short_brief", ""), numeric_values)


def validate_ai_output(output: dict, evidence: list[dict]) -> None:
    """Run all guardrails; raise GuardrailError on the first violation."""
    check_grounding(output, evidence)
    check_monetary_policy(output)
