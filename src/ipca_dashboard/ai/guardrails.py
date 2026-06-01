"""Guardrails: model-independent safety floor for the AI layer (spec_V3 §3.3).

These checks are pure and never change when the model changes. A failure raises
GuardrailError; callers (CP7) catch it and fall back to the deterministic brief,
so the AI can never block the product.

Enforced:
- grounding: every claim cites existing evidence_id(s) (>=1); "regime" also needs
  a rule_id matching ev_regime.
- numbers (anti-hallucination): every number in a claim's text must match a value
  of an evidence THAT CLAIM cites — so a sentence may weave several numbers from
  several cited evidences (readable prose), but cannot quote a number from an
  uncited evidence. The short_brief (which cites nothing) is checked against all
  evidence values.
- monetary policy: tone is from a constrained set; no Copom/Selic forecast or
  asset recommendation; investment_advice must be False.
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

# A claimed figure: a number not attached to letters, and not part of a date
# (hyphen on either side). Skips labels like "12m", "3m", "MM3M", "p80", and
# dates like "2024-03" / "03-2024".
_NUMBER_RE = re.compile(r"(?<![A-Za-z\d-])-?\d+(?:[.,]\d+)?(?![A-Za-z]|[\d-])")

# Known window phrases used as metric labels, not data figures. Keep this narrow:
# arbitrary counts like "9 meses" or "2 anos" must still be grounded.
_KNOWN_WINDOW_PHRASE = re.compile(
    r"\bem\s+12\s+(?:meses|mes|m[eê]s)\b|"
    r"\bm[eé]dia(?:\s+m[oó]vel)?\s+de\s+3\s+(?:meses|mes|m[eê]s)\b",
    re.IGNORECASE,
)


class GuardrailError(ValueError):
    """Raised when AI output violates a guardrail."""


def _normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _has_numeric_unit_after(text: str, end: int) -> bool:
    suffix = text[end : end + 12].lstrip().lower()
    return suffix.startswith(("%", "p.p", "pp", "ponto", "pontos"))


def _is_year_token(raw: str, value: float, text: str, end: int) -> bool:
    # A bare 4-digit integer in the plausible-year range is a date token
    # ("em abril de 2026"), not a data figure. If it carries a numeric unit
    # ("2026%" / "2026 p.p."), treat it as a claimed figure and ground it.
    return (
        raw.isdigit()
        and len(raw) == 4
        and 1900 <= value <= 2100
        and not _has_numeric_unit_after(text, end)
    )


def _numbers_in(text: str) -> list[float]:
    text = text or ""
    # Remove only known metric-window phrases first. Do not blanket-ignore
    # "<count> meses/anos", which can smuggle unsupported factual claims.
    cleaned = _KNOWN_WINDOW_PHRASE.sub(" ", text)
    out: list[float] = []
    for match in _NUMBER_RE.finditer(cleaned):
        m = match.group(0)
        try:
            value = float(m.replace(",", "."))
        except ValueError:
            continue
        if _is_year_token(m, value, cleaned, match.end()):
            continue
        out.append(value)
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


def _cited_values(by_id: dict[str, dict], ids: list[str]) -> list[float]:
    """Numeric values of the evidences a claim cites."""
    values: list[float] = []
    for evidence_id in ids:
        value = by_id.get(evidence_id, {}).get("value")
        if isinstance(value, (int, float)) and value == value:
            values.append(float(value))
    return values


def _require_numbers_in_cited(text: str, cited_values: list[float]) -> None:
    """Every number in the sentence must match a value of an evidence IT cites.

    Stricter than the global check: a claim cannot cite ev_A and quote a number
    that only exists in an uncited ev_B. This preserves anti-hallucination while
    allowing a sentence to weave several numbers from several cited evidences.
    """
    for claimed in _numbers_in(text):
        if not any(_matches(claimed, value) for value in cited_values):
            raise GuardrailError(
                f"Number {claimed} is not grounded in the evidence cited by this claim."
            )


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
            # A 'number' claim may cite >=1 evidences (fluent prose, not a table).
            # Anti-hallucination is preserved — and made stricter — by requiring
            # every number in the sentence to match a value of an evidence IT cites.
            if len(ids) < 1:
                raise GuardrailError("A 'number' claim needs >= 1 evidence_id.")
            _require_numbers_in_cited(text, _cited_values(by_id, ids))
        elif ctype == "interpretation":
            if len(ids) < 1:
                raise GuardrailError("An 'interpretation' claim needs >= 1 evidence_id.")
            _require_numbers_in_cited(text, _cited_values(by_id, ids))
        elif ctype == "regime":
            if not claim.get("rule_id"):
                raise GuardrailError("A 'regime' claim must reference a rule_id.")
            if len(ids) < 1:
                raise GuardrailError("A 'regime' claim needs >= 1 evidence_id.")
            if "ev_regime" in ids and claim.get("rule_id") != by_id["ev_regime"].get(
                "interpretation"
            ):
                raise GuardrailError("A 'regime' claim rule_id does not match ev_regime.")
            _require_numbers_in_cited(text, _cited_values(by_id, ids))
    _require_numbers_in_evidence(output.get("short_brief", ""), numeric_values)


def validate_ai_output(output: dict, evidence: list[dict]) -> None:
    """Run all guardrails; raise GuardrailError on the first violation."""
    check_grounding(output, evidence)
    check_monetary_policy(output)
