"""Useful, key-free answers for common Ask-the-IPCA questions.

This is the availability floor below the live model and audited replay. It does
not infer new facts: it selects current Evidence rows produced by the Tool API,
formats them as short answers, and returns ordinary guarded claims.
"""

from __future__ import annotations

import re
import unicodedata


def _normalize(text: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text or ""))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", plain.lower()).strip()


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value else None


def _shown(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _payload(claims: list[dict]) -> dict | None:
    if not claims:
        return None
    return {
        "answer": " ".join(str(claim["text"]) for claim in claims),
        "claims": claims,
        "monetary_policy_tone": "cautious",
        "investment_advice": False,
    }


def _numeric_claim(text: str, *evidence_ids: str) -> dict:
    return {"text": text, "type": "number", "evidence_ids": list(evidence_ids)}


def _interpretation_claim(text: str, *evidence_ids: str) -> dict:
    return {"text": text, "type": "interpretation", "evidence_ids": list(evidence_ids)}


def _value(by_id: dict[str, dict], evidence_id: str) -> float | None:
    return _number(by_id.get(evidence_id, {}).get("value"))


def _metric_subject(evidence: dict) -> str:
    metric = str(evidence.get("metric", ""))
    return metric.split(":", 1)[-1].strip() or metric


def _item_answer(question: str, by_id: dict[str, dict]) -> dict | None:
    item_rows = {
        evidence_id: row
        for evidence_id, row in by_id.items()
        if evidence_id.startswith(("ev_item_", "ev_weight_"))
        and _number(row.get("value")) is not None
    }
    if not item_rows:
        return None

    wants_weight = bool(re.search(r"\b(peso|pesa|cesta|representa)\w*\b", question))
    wants_contribution = bool(re.search(r"\b(contribui|contribuicao|puxou|impacto)\w*\b", question))
    wants_12m = bool(re.search(r"\b(12m|12 meses|doze meses|anual|acumulad)\w*\b", question))

    if wants_weight:
        prefixes = ("ev_weight_",)
    elif wants_contribution:
        prefixes = ("ev_item_contrib_",)
    elif wants_12m:
        prefixes = ("ev_item_12m_",)
    else:
        prefixes = ("ev_item_mom_", "ev_item_12m_")

    claims: list[dict] = []
    if re.search(r"\b(causa|causou|provou|prova|explica|por que|porque)\b", question):
        claims.append(
            _interpretation_claim(
                "Os dados mostram a variação do item, mas não provam sozinhos por que ela ocorreu."
            )
        )
    for evidence_id, row in item_rows.items():
        if not evidence_id.startswith(prefixes):
            continue
        value = _number(row.get("value"))
        if value is None:
            continue
        subject = _metric_subject(row)
        if evidence_id.startswith("ev_weight_"):
            text = f"O peso de {subject} na cesta é {_shown(value)}%."
        elif evidence_id.startswith("ev_item_contrib_"):
            text = f"A contribuição de {subject} no mês foi {_shown(value)} p.p."
        elif evidence_id.startswith("ev_item_12m_"):
            text = f"{subject} acumula variação de {_shown(value)}% em 12 meses."
        else:
            text = f"{subject} variou {_shown(value)}% no mês."
        claims.append(_numeric_claim(text, evidence_id))
    return _payload(claims)


def _reference_answer(question: str, by_id: dict[str, dict]) -> dict | None:
    def interpretation(evidence_id: str) -> dict | None:
        row = by_id.get(evidence_id)
        text = str(row.get("interpretation", "")).strip() if row else ""
        return _payload([_interpretation_claim(text, evidence_id)]) if text else None

    if re.search(r"\b(ipca-?e)\b", question):
        return interpretation("ev_ref_ipcae")
    if re.search(r"\b(ipca-?15|previa)\b", question):
        return interpretation("ev_ref_ipca15")
    if re.search(r"\binpc\b", question):
        return interpretation("ev_ref_inpc")
    if re.search(r"\b(renda|salarios? minimos?|populacao[- ]alvo)\b", question):
        low, high = _value(by_id, "ev_ref_renda_min"), _value(by_id, "ev_ref_renda_max")
        if low is not None and high is not None:
            return _payload(
                [
                    _numeric_claim(
                        f"O IPCA cobre famílias urbanas com renda de {_shown(low)} a "
                        f"{_shown(high)} salários mínimos, considerando qualquer fonte de renda.",
                        "ev_ref_renda_min",
                        "ev_ref_renda_max",
                    )
                ]
            )
    if re.search(
        r"\b(abrangencia|cobertura|areas? (urbanas?|geograficas?)|cidades|"
        r"quantas?\b.{0,20}\bareas?|onde\b.{0,30}\bcoletad)\w*\b",
        question,
    ):
        value = _value(by_id, "ev_ref_cobertura")
        row = by_id.get("ev_ref_cobertura", {})
        if value is not None:
            claims = [
                _numeric_claim(
                    f"A coleta do IPCA abrange {_shown(value)} áreas urbanas.", "ev_ref_cobertura"
                )
            ]
            detail = str(row.get("interpretation", "")).strip()
            if detail:
                claims.append(_interpretation_claim(detail, "ev_ref_cobertura"))
            return _payload(claims)
    if re.search(r"\b(pof|origem dos pesos|como (?:e|sao) definido\w* os pesos)\b", question):
        return interpretation("ev_ref_pesos_pof")
    if re.search(r"\b(quantos grupos|grupos da cesta|estrutura da cesta)\b", question):
        value = _value(by_id, "ev_ref_grupos")
        row = by_id.get("ev_ref_grupos", {})
        if value is not None:
            return _payload(
                [
                    _numeric_claim(
                        f"A cesta do IPCA se organiza em {_shown(value)} grupos.", "ev_ref_grupos"
                    ),
                    _interpretation_claim(str(row.get("interpretation", "")), "ev_ref_grupos"),
                ]
            )
    if re.search(
        r"\b(calendario|data de divulgacao|periodicidade|"
        r"quando\b.{0,40}\b(?:sai|divulgad))\w*\b",
        question,
    ):
        return interpretation("ev_ref_calendario")
    if re.search(r"\b(periodo[- ]base|numero[- ]indice|base do ipca)\b", question):
        return interpretation("ev_ref_base")
    if re.search(r"\b(fontes? dos dados|de onde vem|tabela sidra)\b", question):
        return interpretation("ev_ref_fontes")
    if re.search(
        r"\b(variacao.+contribuicao|contribuicao.+variacao|pontos percentuais)\b", question
    ):
        return interpretation("ev_ref_variacao_contrib")
    if re.search(r"\b(percentil)\b", question):
        return interpretation("ev_ref_percentil")
    if re.search(r"\b(mm3m|media movel)\b", question) and re.search(
        r"\b(o que|significa|como funciona)\b", question
    ):
        return interpretation("ev_ref_mm3m")
    if re.search(r"\b(ex0|ex3|p55)\b", question):
        match = re.search(r"\b(ex0|ex3|p55)\b", question)
        return interpretation(f"ev_ref_nucleo_{match.group(1)}") if match else None
    if re.search(r"\b(nucleo ms|medias aparadas)\b", question):
        return interpretation("ev_ref_nucleo_ms")
    if re.search(r"\b(nucleo dp|dupla ponderacao)\b", question):
        return interpretation("ev_ref_nucleo_dp")
    if re.search(r"\b(o que (?:e|sao)|significa|definicao)\b", question):
        if "difusao" in question:
            return interpretation("ev_ref_difusao")
        if "nucleo" in question:
            return interpretation("ev_ref_nucleos")
        if "regime" in question:
            return interpretation("ev_ref_regime")
        if "ipca" in question or "inflacao" in question:
            return interpretation("ev_ref_nome")
    return None


def deterministic_answer(question: str, evidence: list[dict]) -> dict | None:
    """Return a guarded direct answer when the evidence supports a known intent."""
    q = _normalize(question)
    by_id = {
        str(row["evidence_id"]): row
        for row in evidence
        if isinstance(row, dict) and row.get("evidence_id")
    }
    if not q or not by_id:
        return None

    item = _item_answer(q, by_id)
    if item is not None:
        return item

    if "regime" in q and re.search(r"\b(atual|qual|como esta|como estamos|agora)\b", q):
        regime = by_id.get("ev_regime")
        if regime:
            claims = [
                {
                    "text": f"O regime atual é {regime.get('value', '')}.",
                    "type": "regime",
                    "evidence_ids": ["ev_regime"],
                    "rule_id": regime.get("interpretation", ""),
                }
            ]
            reference = by_id.get("ev_ref_regime")
            if reference:
                claims.append(
                    _interpretation_claim(str(reference.get("interpretation", "")), "ev_ref_regime")
                )
            return _payload(claims)

    reference = _reference_answer(q, by_id)
    if reference is not None:
        return reference

    claims: list[dict] = []
    if re.search(r"\b(puxou|puxaram|pressionou|contribui|composicao|segurou|aliviou)\w*\b", q):
        headline = _value(by_id, "ev_headline_mom")
        if headline is not None:
            claims.append(
                _numeric_claim(f"O IPCA variou {_shown(headline)}% no mês.", "ev_headline_mom")
            )
        positives = [
            (evidence_id, row)
            for evidence_id, row in by_id.items()
            if evidence_id.startswith("ev_contrib_top_pos_")
            and (_number(row.get("value")) or 0) > 0
        ][:3]
        negatives = [
            (evidence_id, row)
            for evidence_id, row in by_id.items()
            if evidence_id.startswith("ev_contrib_top_neg_")
            and (_number(row.get("value")) or 0) < 0
        ][:2]
        if positives:
            parts = [
                f"{_metric_subject(row)} ({_shown(_number(row['value']) or 0)} p.p.)"
                for _, row in positives
            ]
            claims.append(
                _numeric_claim(
                    "As maiores pressões altistas foram " + ", ".join(parts) + ".",
                    *(item[0] for item in positives),
                )
            )
        if negatives:
            parts = [
                f"{_metric_subject(row)} ({_shown(_number(row['value']) or 0)} p.p.)"
                for _, row in negatives
            ]
            claims.append(
                _numeric_claim(
                    "Os principais alívios foram " + ", ".join(parts) + ".",
                    *(item[0] for item in negatives),
                )
            )
        return _payload(claims)

    if "difusao" in q:
        mom, mm3 = _value(by_id, "ev_diffusion_mom"), _value(by_id, "ev_diffusion_mm3")
        if mom is not None:
            claims.append(
                _numeric_claim(f"A difusão foi de {_shown(mom)}% no mês.", "ev_diffusion_mom")
            )
        if mm3 is not None:
            claims.append(
                _numeric_claim(
                    f"Na média móvel de 3 meses, ficou em {_shown(mm3)}%.", "ev_diffusion_mm3"
                )
            )
        ref = by_id.get("ev_ref_difusao")
        if ref:
            claims.append(
                _interpretation_claim(str(ref.get("interpretation", "")), "ev_ref_difusao")
            )
        return _payload(claims)

    if "nucleo" in q:
        core, headline = _value(by_id, "ev_core_mean_mom"), _value(by_id, "ev_headline_mom")
        if core is not None:
            claims.append(
                _numeric_claim(
                    f"A média dos núcleos variou {_shown(core)}% no mês.", "ev_core_mean_mom"
                )
            )
        if headline is not None:
            claims.append(
                _numeric_claim(
                    f"No mesmo período, o IPCA cheio variou {_shown(headline)}%.", "ev_headline_mom"
                )
            )
        core_mm3 = _value(by_id, "ev_core_mean_mm3")
        if core_mm3 is not None:
            claims.append(
                _numeric_claim(
                    f"A média móvel de 3 meses dos núcleos está em {_shown(core_mm3)}%.",
                    "ev_core_mean_mm3",
                )
            )
        return _payload(claims)

    if "regime" in q:
        regime = by_id.get("ev_regime")
        if regime:
            claims.append(
                {
                    "text": f"O regime atual é {regime.get('value', '')}.",
                    "type": "regime",
                    "evidence_ids": ["ev_regime"],
                    "rule_id": regime.get("interpretation", ""),
                }
            )
        return _payload(claims)

    if re.search(r"\b(causa|causou|provou|prova|explica|por que|porque)\b", q):
        return _payload(
            [
                _interpretation_claim(
                    "Os dados do IPCA mostram o que variou, mas não provam sozinhos "
                    "uma causa externa. Para testar a hipótese, nomeie o item ou grupo "
                    "por onde o efeito deveria aparecer."
                )
            ]
        )

    if re.search(
        r"\b(saar|ajuste sazonal|ajustad\w* sazonal|dessazonal|aceler\w*|momentum|ritmo recente)\b",
        q,
    ):
        sa = _value(by_id, "ev_headline_saar_sa")
        nsa = _value(by_id, "ev_headline_mm3")
        if sa is not None:
            claims.append(
                _numeric_claim(
                    f"O IPCA roda a {_shown(sa)}% ao ano no ritmo de 3 meses dessazonalizado por STL.",
                    "ev_headline_saar_sa",
                )
            )
        if nsa is not None:
            claims.append(
                _numeric_claim(
                    f"A média móvel bruta de 3 meses está em {_shown(nsa)}%.", "ev_headline_mm3"
                )
            )
        return _payload(claims)

    mom, yoy = _value(by_id, "ev_headline_mom"), _value(by_id, "ev_headline_12m")
    if re.search(r"\b(12m|12 meses|doze meses|anual|acumulad)\w*\b", q):
        if yoy is not None:
            claims.append(
                _numeric_claim(f"O IPCA acumula {_shown(yoy)}% em 12 meses.", "ev_headline_12m")
            )
        if mom is not None:
            claims.append(
                _numeric_claim(f"No mês mais recente, variou {_shown(mom)}%.", "ev_headline_mom")
            )
        return _payload(claims)

    if re.search(r"\b(ipca|inflacao|headline|preco\w*|subiu|caiu|variou)\b", q):
        if mom is not None:
            claims.append(
                _numeric_claim(
                    f"O IPCA variou {_shown(mom)}% no mês mais recente.", "ev_headline_mom"
                )
            )
        if yoy is not None:
            claims.append(
                _numeric_claim(
                    f"O acumulado em 12 meses está em {_shown(yoy)}%.", "ev_headline_12m"
                )
            )
        return _payload(claims)
    return None
