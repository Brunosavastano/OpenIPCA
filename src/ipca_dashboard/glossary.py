"""Plain-language glossary — the single source of truth for tooltips and the
in-app glossary section (spec_V3 audience: LinkedIn readers without macro context).

# REVISAR (Bruno): estas são definições em linguagem leiga rascunhadas para
# legibilidade. Revise a PRECISÃO ECONÔMICA de cada uma antes do merge — você tem
# a palavra final. O objetivo é "entendível por quem não é economista", não um
# verbete técnico.

Lookup is tolerant to case and accents via `describe()`.
"""

from __future__ import annotations

import unicodedata

# Card metrics shown on the executive panel (used as st.metric(help=...)).
CARD_TERMS: dict[str, str] = {
    "IPCA m/m": (
        "Inflação do mês: quanto os preços subiram, em média, no mês de referência "
        "em relação ao mês anterior."
    ),
    "IPCA 12m": (
        "Inflação acumulada nos últimos 12 meses — a medida mais usada para dizer "
        "'a inflação está em X%'."
    ),
    "IPCA MM3M": (
        "Ritmo recente: média da inflação dos últimos 3 meses. Suaviza altos e "
        "baixos para mostrar a tendência de curto prazo. (NSA = sem ajuste sazonal.)"
    ),
    "Média núcleos MM3M": (
        "Ritmo recente dos 'núcleos' (média de 3 meses). Núcleos tiram os itens mais "
        "instáveis para revelar a tendência de fundo da inflação."
    ),
    "Difusão MM3M": (
        "Quão espalhada está a alta de preços: % de itens da cesta que subiram "
        "(média de 3 meses). Alto = inflação disseminada; baixo = concentrada em poucos itens."
    ),
    "Alertas ativos": (
        "Quantos sinais de atenção a metodologia acendeu neste mês (ex.: núcleos altos, "
        "inflação muito espalhada). Cada alerta é uma regra objetiva, não opinião."
    ),
}

# Core concepts (for the in-app glossary expander).
CONCEPTS: dict[str, str] = {
    "inflacao": (
        "Inflação (IPCA): índice oficial do Brasil (medido pelo IBGE) que mede a "
        "variação média dos preços de uma cesta de produtos e serviços."
    ),
    "variacao": (
        "Variação (%): quanto o preço médio de um grupo ou item mudou no mês, em "
        "relação ao mês anterior. É o número que o IBGE divulga (ex.: 'Alimentação "
        "subiu 1,34%')."
    ),
    "contribuicao": (
        "Contribuição (p.p.): quanto um grupo ou item puxou da inflação cheia do mês, "
        "em pontos percentuais do IPCA. Calcula-se como variação × peso ÷ 100 — por "
        "isso um item pode variar muito e contribuir pouco se tiver peso pequeno."
    ),
    "peso": (
        "Peso (%): a fatia do orçamento das famílias que um grupo ou item representa "
        "na cesta do IPCA. Quanto maior o peso, mais a variação daquele item mexe no "
        "índice cheio."
    ),
    "nucleos": (
        "Núcleos de inflação: versões do IPCA que excluem ou suavizam os itens mais "
        "voláteis (como alimentos in natura e energia). Servem para ver a tendência de "
        "fundo, sem o 'barulho' de choques temporários."
    ),
    "difusao": (
        "Difusão: % dos itens da cesta que subiram de preço no período. Alta difusão "
        "significa que a inflação está espalhada por muitos itens — sinal mais "
        "preocupante do que uma alta concentrada em um ou dois itens."
    ),
    "mm3m": (
        "MM3M: média móvel de 3 meses. Em vez de olhar um mês isolado (que pode ser "
        "atípico), olha a média dos últimos 3 meses para ver o ritmo recente."
    ),
    "nsa": (
        "NSA (sem ajuste sazonal): o número não foi corrigido para efeitos típicos da "
        "época do ano. A versão com ajuste sazonal está planejada para uma próxima versão."
    ),
    "regime": (
        "Regime inflacionário: um rótulo que resume o quadro do mês combinando o nível "
        "da inflação com o quão espalhada ela está, comparando o mês atual com a "
        "história desde 2012. É calculado por uma regra fixa, não pela IA."
    ),
    "alertas": (
        "Alertas: sinais de atenção disparados por regras objetivas (ex.: núcleos acima "
        "de um limite). Não são recomendações nem previsões — apenas marcam o que merece "
        "olhar com cuidado."
    ),
}

# Regime labels -> one-line plain explanation (badge + glossary).
REGIME_TERMS: dict[str, str] = {
    "Pressão disseminada": (
        "Pressão disseminada: a alta de preços está espalhada pela maioria dos itens, "
        "não concentrada em poucos."
    ),
    "Desinflação disseminada": (
        "Desinflação disseminada: a maior parte dos itens está desacelerando — quadro "
        "mais benigno."
    ),
    "Desinflação frágil": (
        "Desinflação frágil: a inflação cheia cedeu, mas ainda está espalhada por muitos "
        "itens — alívio pouco consolidado."
    ),
    "Choque localizado": (
        "Choque localizado: a inflação subiu, mas concentrada em poucos itens — menos "
        "preocupante que uma alta generalizada."
    ),
    "Quadro misto": (
        "Quadro misto: os sinais não apontam todos na mesma direção; leitura sem "
        "tendência clara."
    ),
    "Dados insuficientes": (
        "Dados insuficientes: não há base suficiente no mês para classificar o regime "
        "com segurança."
    ),
}

# Individual IPCA cores (BCB). Plain one-liners — REVISAR (Bruno).
CORE_TERMS: dict[str, str] = {
    "EX0": "EX0: núcleo por exclusão — tira do IPCA itens muito voláteis (alimentos no "
           "domicílio e energia) para mostrar a tendência de fundo.",
    "EX1": "EX1: núcleo por exclusão — remove um conjunto de itens voláteis (variante "
           "do EX0) para revelar a tendência subjacente.",
    "EX2": "EX2: núcleo por exclusão — exclui alimentos no domicílio e combustíveis, "
           "entre outros voláteis.",
    "EX3": "EX3: núcleo por exclusão — exclui alimentos no domicílio e itens de energia; "
           "muito acompanhado pelo Banco Central.",
    "EX_FE": "EX-FE: núcleo que exclui alimentos e energia ('food & energy'), os dois "
             "grupos mais sujeitos a choques temporários.",
    "DP": "DP (dupla ponderação): núcleo que dá menos peso aos itens mais voláteis, em "
          "vez de excluí-los, para suavizar choques.",
    "MA": "MA (médias aparadas): núcleo que descarta os itens com as maiores e menores "
          "variações do mês e calcula a média do meio.",
    "MS": "MS (médias aparadas com suavização): como o MA, mas suaviza itens cujos "
          "preços mudam com pouca frequência.",
    "P55": "P55: núcleo de percentil — pega a variação do item que está na posição 55% "
           "da distribuição, uma medida robusta de tendência central.",
}

# Severity translation (alerts).
SEVERITY_PT: dict[str, str] = {
    "critical": "crítico",
    "high": "alto",
    "medium": "médio",
    "low": "baixo",
    "info": "informativo",
}

# Friendly labels for the momentum metrics (single source — used by the cores
# page selectbox AND the chart titles, so they never diverge).
METRIC_LABELS: dict[str, str] = {
    "mom": "no mês (m/m)",
    "rolling_12m": "em 12 meses",
    "moving_average_3m": "média de 3 meses (MM3M, sem ajuste sazonal)",
    "three_month_saar": "3 meses anualizado (NSA, experimental)",
}


def metric_label(key: str) -> str:
    """Friendly label for a momentum metric key; falls back to the key itself."""
    return METRIC_LABELS.get(key, key)

# Unified lookup table.
_ALL: dict[str, str] = {**CARD_TERMS, **CONCEPTS, **REGIME_TERMS, **CORE_TERMS}


def _normalize(key: str) -> str:
    decomposed = unicodedata.normalize("NFKD", key or "")
    no_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return no_accents.strip().lower()


_NORMALIZED = {_normalize(k): v for k, v in _ALL.items()}


def describe(key: str) -> str:
    """Return the plain-language definition for a term, or '' if unknown.

    Tolerant to case and accents (e.g. 'Difusão', 'difusao', 'DIFUSAO' all match).
    """
    return _NORMALIZED.get(_normalize(key), "")
