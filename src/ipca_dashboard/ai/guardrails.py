"""Guardrails: model-independent safety floor for the AI layer (spec_V3 §3.3).

These checks are pure and never change when the model changes. A failure raises
GuardrailError; callers (CP7) catch it and fall back to the deterministic brief,
so the AI can never block the product.

Enforced:
- grounding: 'number' and 'regime' claims cite existing evidence_id(s) (>=1);
  "regime" also needs a rule_id matching ev_regime. A 'interpretation' claim with
  NO number may stand without a citation (the qualitative reasoning the Q&A prompt
  invites), but the moment it states a number that number must match a cited
  evidence value — so the "every NUMBER is traceable" thesis is unchanged.
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
        r"reduza|baixa|baixara|baixar|sobe|subira|subir|eleva|elevara|elevar|"
        r"aumenta|aumentara|aumentar|mantem|mantera|manter|mantenha)\b"
    ),
    re.compile(
        r"\bselic\b.{0,40}\b"
        r"(vai|deve|ira|sera|cai|caia|caira|cair|cortada|reduzida|sobe|subira|subir|"
        r"elevada|aumentada|mantida|fica|ficara|fique)\b"
    ),
    re.compile(
        r"\b(corte|alta|queda|manutencao)\s+(da\s+selic|de\s+juros)\s+(?:e\s+)?"
        r"(certo|garantid|inevitavel)\w*\b"
    ),
    re.compile(
        r"\b(banco\s+central|bc|bcb)\b.{0,40}\b"
        r"(vai|deve|ira|corta|cortara|cortar|reduz|reduzira|reduzir|reduza|"
        r"baixa|baixara|baixar|sobe|subira|subir|eleva|elevara|elevar|"
        r"aumenta|aumentara|aumentar|mantem|mantera|manter|mantenha)\b"
        r".{0,30}\b(juros|selic)\b"
    ),
    re.compile(
        r"\b(compre|compra|comprar|venda|vender|invista|investir|aplique|aplicar|"
        r"aloque|alocar|aposte|apostar)\b.{0,40}\b"
        r"(acao|acoes|ativo|ativos|dolar|tesouro|ipca\+|ntn-?b|bova11|ivvb11|"
        r"fundo|fundos|titulo|titulos)\b"
    ),
    re.compile(
        r"\b(monte|montar|abra|abrir|faca|fazer)\b.{0,30}\b"
        r"(posicao|exposicao)\b.{0,40}\b"
        r"(acao|acoes|ativo|ativos|dolar|tesouro|ipca\+|ntn-?b|bova11|ivvb11|"
        r"fundo|fundos|titulo|titulos)\b"
    ),
    re.compile(
        r"\b(recomendo|recomenda|recomendar|recomendaria|sugiro|indico|indicaria)\b.{0,40}\b"
        r"(acao|acoes|ativo|ativos|dolar|tesouro|ipca\+|ntn-?b|selic|fundo|fundos|"
        r"titulo|titulos)\b"
    ),
]

# Substring hints (matched on accent-stripped lowercase text) that mark a question
# as in-scope for the public "Pergunte ao IPCA" box. The user is already in the
# IPCA box, so this is a cheap first gate: anything WITHOUT a price/consumption/
# methodology term (e.g. "qual a previsão do tempo?") is refused before the model,
# saving quota and keeping the answers on-brand. Kept generous on purpose — a
# legitimate basket question ("passagem aérea e arroz têm pesos diferentes?") must
# pass — but each stem is specific enough not to turn the gate into a no-op (avoid
# substrings of common unrelated words like "cont", "alta", "cara").
_IN_SCOPE_HINTS = [
    # Core IPCA concepts
    "ipca",
    "inflacao",
    "nucleo",
    "difusao",
    "headline",
    "regime",
    "contribuicao",
    # Basket / weights / structure
    "preco",
    "peso",
    "cesta",
    "item",
    "itens",
    "subitem",
    "subgrupo",
    "grupo",
    "produto",
    "servico",
    # Price movement vocabulary
    "cust",
    "caro",
    "barat",
    "subi",
    "caiu",
    "cair",
    "queda",
    "aument",
    "encarec",
    "reajust",
    # Common basket categories
    "gasolina",
    "combustivel",
    "aliment",
    "comida",
    "energia",
    "aluguel",
    "tarifa",
    "passagem",
    "transporte",
    "saude",
    "educacao",
    "vestuario",
    "remedio",
    # Sources / methodology
    "ibge",
    "pof",
    "sidra",
    "sgs",
    "sazonal",
    "anualizado",
    "acumulado",
    "percentil",
    "mm3m",
]

# Prompt-injection / jailbreak markers. A PUBLIC free-text box invites attempts to
# override the system prompt ("ignore your instructions", "you are now ...") so
# the model says something off-brand with the owner's name on it. We refuse the
# QUESTION before it ever reaches the model (defence in depth; the system prompt
# also tells the model to ignore embedded commands). Matched on accent-stripped
# lowercase text, like _FORBIDDEN_PATTERNS.
_INJECTION_PATTERNS = [
    re.compile(r"\bignore?\b.{0,30}\b(instru\w*|prompt|regras|orienta\w*|tudo|acima)\b"),
    re.compile(r"\b(desconsidere|esque[cç]a|apague|desfa[cç]a)\b.{0,30}\b(instru\w*|prompt|regras|acima|anterior\w*|tudo|contexto)\b"),
    re.compile(r"\b(you are now|act as|pretend to be|disregard|forget (the|all|your)|system prompt|jailbreak|developer mode)\b"),
    re.compile(r"\b(aja como|finja (ser|que)|voce agora e|a partir de agora voce|assuma o papel)\b"),
    re.compile(r"\b(responda como se|fa[cç]a de conta|ignore o contexto|sem restri[cç]\w*)\b"),
]

# Same intent, but matched on a compact skeleton that strips spaces, zero-width
# separators and punctuation. This catches "i g n o r e" / "ig\u200bnore" without
# refusing benign words like "ignorada" or "acima" on their own.
_COMPACT_INJECTION_PATTERNS = [
    re.compile(
        r"ignore(?:a|as|o|os|suas|todas|todos|all|previous|your|the)*"
        r"(instrucoes|instructions|prompt|regras|rules|acima|anteriores|previous|"
        r"contexto|context|tudo|systemprompt)"
    ),
    re.compile(
        r"(desconsidere|esqueca|forget|disregard)"
        r"(instrucoes|instructions|prompt|regras|rules|acima|anteriores|previous|"
        r"contexto|context|tudo|all)"
    ),
    re.compile(
        r"(youarenow|actas|pretendtobe|ajacomo|voceagorae|apartirdeagoravoce|"
        r"assumaopapel|developermode|jailbreak)"
    ),
]

# A claimed figure: a number not attached to letters, and not part of a date
# (hyphen on either side). Skips labels like "12m", "3m", "MM3M", "p80", and
# dates like "2024-03" / "03-2024".
_NUMBER_RE = re.compile(r"(?<![A-Za-z\d-])-?\d+(?:[.,]\d+)?(?![A-Za-z]|[\d-])")

# Metric-window labels, not data figures. The integer in "<window> meses" is the
# lookback length of a rolling metric (12m, MM3M, MM6M, the 24-month charts), so
# "12 meses" / "3 meses" must not be treated as ungrounded numbers — that false
# positive was silently rejecting valid live Q&A answers (the model phrases the
# window many ways: "acumulado de 12 meses", "núcleo de 3 meses", "nos últimos 6
# meses"). Restricted to the windows the product actually uses (3, 6, 12, 24):
# arbitrary counts like "9 meses" or "2 anos" must STILL be grounded, so a model
# cannot smuggle an unsupported "in the last N ..." claim. The data values
# themselves (4,39%, 0,67 p.p.) carry units and are grounded as usual — only the
# bare window integer bound to a month-word is dropped.
_KNOWN_WINDOW_PHRASE = re.compile(
    r"\b(?:3|6|12|24)\s+(?:meses|m[eê]s)\b",
    re.IGNORECASE,
)


class GuardrailError(ValueError):
    """Raised when AI output violates a guardrail."""


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _compact_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text)


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


def _all_claim_cited_values(by_id: dict[str, dict], claims: list[dict]) -> list[float]:
    values: list[float] = []
    for claim in claims:
        values.extend(_cited_values(by_id, claim.get("evidence_ids", []) or []))
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


def check_injection(question: str) -> None:
    """Refuse a question that tries to override the system prompt (jailbreak)."""
    text = _normalize_text(question or "")
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            raise GuardrailError("Refused: the input looks like a prompt-injection attempt.")
    compact = _compact_text(text)
    for pat in _COMPACT_INJECTION_PATTERNS:
        if pat.search(compact):
            raise GuardrailError("Refused: the input looks like a prompt-injection attempt.")


def check_question(question: str) -> None:
    """Run all input-side guardrails for a public Q&A box (injection then scope)."""
    check_injection(question)
    check_scope(question)


def check_monetary_policy(output: dict) -> None:
    tone = output.get("monetary_policy_tone")
    if tone is not None and tone not in MONETARY_POLICY_TONES:
        raise GuardrailError(f"Invalid monetary_policy_tone: {tone!r}")
    if output.get("investment_advice", False):
        raise GuardrailError("investment_advice must be False.")
    # Scan every user-facing text field: the brief uses short_brief, the Q&A uses
    # `answer`. Both must be checked so a forecast can't hide in the answer prose.
    blob = _normalize_text(
        " ".join(
            [output.get("short_brief", ""), output.get("answer", "")]
            + [c.get("text", "") for c in output.get("claims", [])]
        )
    )
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(blob):
            raise GuardrailError(f"Forbidden monetary-policy/investment language: /{pat.pattern}/")


def check_grounding(output: dict, evidence: list[dict]) -> None:
    by_id = {ev["evidence_id"]: ev for ev in evidence}
    numeric_values = _numeric_evidence_values(evidence)
    claims = output.get("claims", []) or []
    for claim in claims:
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
            # A number-free interpretation is the qualitative reasoning the Q&A
            # prompt explicitly invites — it may stand without an evidence_id. The
            # moment it states a number, that number must match a cited evidence
            # value: _require_numbers_in_cited([]) rejects any number when nothing
            # is cited, and the answer-level number guard below is unchanged. So no
            # ungrounded NUMBER can slip through; only qualitative prose is freed.
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
    # The brief's short_brief cites no specific ids, so check against all values.
    _require_numbers_in_evidence(output.get("short_brief", ""), numeric_values)
    # The Q&A answer is accompanied by claims. Any number in the user-facing
    # answer must be covered by at least one evidence_id cited by those claims.
    _require_numbers_in_cited(output.get("answer", ""), _all_claim_cited_values(by_id, claims))


def validate_ai_output(output: dict, evidence: list[dict]) -> None:
    """Run all guardrails; raise GuardrailError on the first violation."""
    check_grounding(output, evidence)
    check_monetary_policy(output)
