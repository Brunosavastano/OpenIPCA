"""English Q&A presentation and bilingual retrieval; no model calls or data changes."""
from __future__ import annotations

import re

from ipca_dashboard.english_items import ITEM_LABELS
from ipca_dashboard.glossary_en import REGIME_LABELS

CURATED_QUESTIONS = [
    "What drove IPCA inflation this month?",
    "Is inflation broad-based or concentrated? How is diffusion?",
    "How do IPCA core measures compare with headline inflation?",
    "What is the current inflation regime and what does it mean?",
    "Did food push inflation up or down this month?",
    "What is cumulative inflation over 12 months?",
]
REFUSAL = (
    "I can answer questions about Brazilian inflation (IPCA) using the available official "
    "data. Ask about monthly drivers, the spread of price increases, or core inflation. "
    "I cannot provide investment recommendations or forecasts of Copom decisions."
)
FALLBACK = (
    "There is not enough evidence to answer this question reliably. Try the monthly "
    "result, twelve-month inflation, diffusion, core measures, the inflation regime, "
    "the largest contributions, or a named basket item."
)
QUERY_TERMS = {
    **{english.lower(): portuguese for portuguese, english in ITEM_LABELS.items()},
    "what drove": "o que puxou", "drove": "puxou", "push": "puxou",
    "food": "Alimentação e bebidas", "inflation": "inflação", "diffusion": "difusão",
    "core measures": "núcleos", "core inflation": "núcleos", "cores": "núcleos",
    "current": "atual", "what is": "o que é", "what are": "o que são",
    "how": "como", "mean": "significa", "12 months": "12 meses",
    "twelve months": "doze meses", "cumulative": "acumulada",
    "weight": "peso", "weights": "pesos", "basket": "cesta",
    "contribution": "contribuição", "contributions": "contribuições",
    "price": "preço", "prices": "preços", "change": "variação",
    "seasonal adjustment": "ajuste sazonal", "seasonally adjusted": "ajuste sazonal",
    "moving average": "média móvel", "percentile": "percentil",
    "income": "renda", "coverage": "cobertura", "release date": "data de divulgação",
    "schedule": "calendário", "data sources": "fontes dos dados",
    "base period": "período-base", "percentage points": "pontos percentuais",
    "why": "por que", "cause": "causa", "caused": "causou",
    "how many groups": "quantos grupos", "trimmed means": "médias aparadas",
    "double weighting": "dupla ponderação", "core ms": "núcleo MS", "core dp": "núcleo DP",
}
_QUERY = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(k) for k in sorted(QUERY_TERMS, key=len, reverse=True)) + r")(?!\w)", re.I)


def retrieval_question(question: str) -> str:
    """Translate known terms, leaving unknown text intact for injection checks."""
    curated = dict(zip(CURATED_QUESTIONS, [
        "O que mais puxou a inflação do IPCA neste mês?",
        "A inflação está espalhada ou concentrada? Como está a difusão?",
        "Como estão os núcleos do IPCA em relação ao headline?",
        "Qual é o regime inflacionário atual e o que ele significa?",
        "Alimentação e bebidas puxou ou segurou a inflação do mês?",
        "Como está a inflação acumulada em 12 meses?",
    ], strict=True))
    for original, translated in curated.items():
        if question.strip().casefold() == original.casefold():
            return translated
    return _QUERY.sub(lambda m: QUERY_TERMS[m.group().lower()], question)


# Translations of the existing source-backed corpus. IDs, values, dates and URLs stay intact.
REFERENCE_TEXT = {
    "nome": "IPCA is Brazil's official broad consumer price index, calculated and published by IBGE, the Brazilian Institute of Geography and Statistics. It is the reference index for the Central Bank's inflation-targeting framework.",
    "base": "The IPCA index has a December 1993 base of 100. Monthly, year-to-date and twelve-month changes are calculated from this linked index.",
    "renda_min": "IPCA covers urban households earning at least one minimum wage, from any income source, in the surveyed areas.",
    "renda_max": "The upper income limit is forty minimum wages, covering most Brazilian urban households.",
    "cobertura": "The survey covers sixteen urban areas: São Paulo, Rio de Janeiro, Belo Horizonte, Porto Alegre, Curitiba, Salvador, Recife, Fortaleza, Belém, Vitória, Brasília, Goiânia, Campo Grande, Rio Branco, São Luís and Aracaju.",
    "pesos_pof": "Basket weights come from IBGE's Household Budget Survey (POF), which measures household spending patterns. The current structure is based on the 2017–2018 survey, incorporated in January 2020, and changes when a new survey is adopted.",
    "grupos": "The basket has nine groups: Food and beverages, Housing, Household goods, Clothing, Transportation, Health and personal care, Personal expenses, Education, and Communication. Each divides into subgroups, items and subitems.",
    "calendario": "IBGE releases IPCA monthly, usually in the first half of the following month. Exact dates are published in the official release calendar.",
    "inpc": "INPC uses the same price collection as IPCA but represents lower-income households earning one to five minimum wages, which are more sensitive to essentials such as food, transport and medicines.",
    "ipca15": "IPCA-15 is an advance inflation indicator. Its price collection period runs approximately from the sixteenth of the preceding month to the fifteenth of the reference month. Geographic coverage may also differ from the full IPCA.",
    "ipcae": "IPCA-E is the quarterly cumulative change in IPCA-15.",
    "variacao_contrib": "Price change (%) measures how much an item's price moved. Contribution (percentage points) measures its impact on headline inflation: price change multiplied by basket weight, divided by one hundred. A large price change can have a small impact when the item's weight is low.",
    "periodos": "Monthly inflation compares prices with the preceding month. Year-to-date inflation compounds changes from January. Twelve-month inflation compounds the latest twelve monthly changes; it is not a simple sum.",
    "nucleos": "Core measures exclude or smooth volatile items, such as fresh food and energy, to reveal underlying inflation. The Central Bank monitors several measures.",
    "difusao": "Diffusion is the unweighted share of surveyed IPCA subitems with rising prices. High diffusion indicates broad-based price pressure rather than increases concentrated in a few items.",
    "mm3m": "The three-month moving average smooths monthly inflation to show its recent pace. This measure is presented without seasonal adjustment.",
    "nsa": "NSA means not seasonally adjusted. Seasonal patterns remain in the monthly data. The app also provides a separate experimental STL-adjusted series, labeled SA; it is not an official IBGE or BCB adjustment.",
    "percentil": "The historical percentile compares the latest value with the available series since 2012, using an expanding window and accounting for ties.",
    "regime": "The inflation regime is a rule-based classification, not an AI judgment. It combines inflation levels and the breadth of price increases relative to their history since 2012.",
    "fontes": "The app uses official data: IBGE/SIDRA table 7060 for the basket hierarchy, weights and price changes, and BCB/SGS for headline inflation, aggregates, core measures and official diffusion.",
    "nucleo_ex0": "EX0 is a Central Bank exclusion measure. It includes market-determined IPCA prices except food consumed at home, to highlight underlying inflation.",
    "nucleo_ex3": "EX3 is derived from EX2 and comprises its services and industrial-goods cores, excluding food consumed at home.",
    "nucleo_ms": "MS is a smoothed trimmed-mean measure: it trims the largest and smallest monthly price changes and smooths items whose prices change infrequently.",
    "nucleo_dp": "DP uses double weighting to reduce the influence of volatile items rather than excluding them.",
    "nucleo_p55": "P55 uses the price change at the 55th percentile of the monthly distribution as a robust measure of central tendency.",
}
REFERENCE_LABELS = {
    "nome": "What IPCA measures", "base": "IPCA base period",
    "renda_min": "Minimum household income", "renda_max": "Maximum household income",
    "cobertura": "Geographic coverage", "pesos_pof": "Source of basket weights",
    "grupos": "IPCA basket groups", "calendario": "Release calendar",
    "inpc": "INPC", "ipca15": "IPCA-15", "ipcae": "IPCA-E",
    "variacao_contrib": "Price change and contribution", "periodos": "Measurement periods",
    "nucleos": "Core inflation", "difusao": "Inflation diffusion",
    "mm3m": "Three-month moving average", "nsa": "Seasonal adjustment",
    "percentil": "Historical percentile", "regime": "Inflation regime",
    "fontes": "Official data sources", "nucleo_ex0": "EX0 core measure",
    "nucleo_ex3": "EX3 core measure", "nucleo_ms": "MS core measure",
    "nucleo_dp": "DP core measure", "nucleo_p55": "P55 core measure",
}
PHRASES = {
    **ITEM_LABELS, **REGIME_LABELS,
    "Os dados mostram a variação do item, mas não provam sozinhos por que ela ocorreu.": "The data show the item's price change, but do not by themselves establish its cause.",
    "Os dados do IPCA mostram o que variou, mas não provam sozinhos uma causa externa. Para testar a hipótese, nomeie o item ou grupo por onde o efeito deveria aparecer.": "IPCA data show what changed, but do not by themselves establish an external cause. To examine the hypothesis, name the item or group through which the effect would appear.",
    "O peso de ": "The basket weight of ", " na cesta é ": " is ",
    "A contribuição de ": "The contribution from ", " no mês foi ": " this month was ",
    " acumula variação de ": " changed by ", " em 12 meses.": "%WINDOW%",
    " variou ": " changed by ", " no mês mais recente.": " in the latest month.",
    " no mês.": " this month.",
    "O IPCA cobre famílias urbanas com renda de ": "IPCA covers urban households earning ",
    " salários mínimos, considerando qualquer fonte de renda.": " minimum wages, from any income source.",
    "A coleta do IPCA abrange ": "IPCA price collection covers ", " áreas urbanas.": " urban areas.",
    "A cesta do IPCA se organiza em ": "The IPCA basket is organized into ", " grupos.": " groups.",
    "O regime atual é ": "The current regime is ", "O IPCA variou ": "IPCA changed by ",
    "As maiores pressões altistas foram ": "The largest upward contributions were ",
    "Os principais alívios foram ": "The largest downward contributions were ",
    "A difusão foi de ": "Diffusion was ",
    "Na média móvel de 3 meses, ficou em ": "Its three-month moving average was ",
    "A média dos núcleos variou ": "Mean core inflation was ",
    "No mesmo período, o IPCA cheio variou ": "Over the same period, headline IPCA changed by ",
    "A média móvel de 3 meses dos núcleos está em ": "The three-month average of core inflation was ",
    "O IPCA roda a ": "IPCA is running at ",
    "% ao ano no ritmo de 3 meses dessazonalizado por STL.": "% on a three-month annualized basis, seasonally adjusted using STL.",
    "A média móvel bruta de 3 meses está em ": "The unadjusted three-month moving average was ",
    "O IPCA acumula ": "Cumulative IPCA inflation was ",
    "No mês mais recente, variou ": "In the latest month, it changed by ",
    "O acumulado em 12 meses está em ": "Twelve-month inflation was ",
    "Peso na cesta: ": "Basket weight: ", "Variação mensal: ": "Monthly change: ",
    "Variação em 12 meses: ": "Twelve-month change: ", "Contribuição mensal: ": "Monthly contribution: ",
    "Variação no mês: ": "Monthly change: ", "Contribuição no mês: ": "Monthly contribution: ",
    "Contribuição: ": "Contribution: ", "Difusão": "Diffusion", "Média núcleos": "Core mean",
    "MM3M": "3M average", "percentil": "percentile", "Regime inflacionário": "Inflation regime",
    "3m anualizado": "3M annualized", "Alerta: ": "Alert: ",
}
_PHRASES = re.compile("|".join(re.escape(k) for k in sorted(PHRASES, key=len, reverse=True)))


def answer_text(text: str) -> str:
    result = _PHRASES.sub(lambda m: PHRASES[m.group()], text)
    result = result.replace("%WINDOW%", " over twelve months.")
    result = re.sub(r"(?<=\d),(?=\d)", ".", result)
    return re.sub(r"(?<=\d) a (?=\d)", " to ", result)


def english_evidence(evidence: list[dict]) -> list[dict]:
    rows = []
    for original in evidence:
        row = dict(original)
        key = str(row.get("evidence_id", ""))
        if key.startswith("ev_ref_") and key[7:] in REFERENCE_TEXT:
            row["interpretation"] = REFERENCE_TEXT[key[7:]]
            row["metric"] = REFERENCE_LABELS[key[7:]]
        else:
            row["metric"] = answer_text(str(row.get("metric", "")))
        row["unit"] = {"texto": "text", "áreas": "areas", "grupos": "groups", "salário mínimo": "minimum wage", "salários mínimos": "minimum wages", "índice (base)": "index (base)", "tabela SIDRA": "SIDRA table", "percentil": "percentile", "% de subitens": "% of subitems", "% a.a.": "% annualized"}.get(row.get("unit"), row.get("unit"))
        rows.append(row)
    return rows


def english_payload(payload: dict | None) -> dict | None:
    if payload is None:
        return None
    result = dict(payload)
    result["claims"] = [dict(claim, text=answer_text(claim["text"])) for claim in payload["claims"]]
    result["answer"] = " ".join(claim["text"] for claim in result["claims"])
    return result
