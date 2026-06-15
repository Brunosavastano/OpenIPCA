# Metodologia

## Fontes

### BCB/SGS

Usado para IPCA headline, agregados macro, núcleos de inflação, difusão oficial e séries subjacentes EX3. A configuração fica em `config/series_sgs.yaml`.

Endpoint padrao:

```text
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODIGO}/dados?formato=json
```

### IBGE/SIDRA

Usado para a decomposição por grupo, subgrupo, item e subitem. A configuração fica em `config/sidra_7060.yaml`.

Tabela 7060:

- `63`: variação mensal do IPCA;
- `66`: peso mensal;
- `69`: variação acumulada no ano;
- `2265`: variação acumulada em 12 meses.

## Transformacoes

### Contribuição mensal

```text
contrib_i,t = peso_i,t * variacao_i,t / 100
```

A contribuição é expressa em pontos percentuais. A validação principal compara a soma das contribuições por grupo com o headline mensal.

### IPCA 12 meses

Para séries mensais do SGS, o acumulado em 12 meses é calculado por encadeamento:

```text
100 * (prod(1 + x_t/100, 12 meses) - 1)
```

### Momentum de curto prazo (MM3M, sem ajuste sazonal)

As variações mensais do IPCA são **brutas (NSA)**, sem ajuste sazonal. Por isso, o
dashboard apresenta o momentum de curto prazo como **MM3M** — média móvel de 3 meses da
variação m/m — e **não** como taxa anualizada (SAAR). Anualizar uma série NSA elevaria o
padrão sazonal à quarta potência e o rótulo "SAAR" (*Seasonally Adjusted Annual Rate*)
seria incorreto sobre dado sem ajuste.

A coluna `three_month_saar` permanece calculada internamente para auditoria e exploração
(rotulada como "3m anualizado (NSA, experimental)"), mas não é a métrica de destaque.

```text
MM3M_t = média(x_t, x_{t-1}, x_{t-2})            # m/m, sem ajuste sazonal
3m anualizado (NSA) = 100 * [((1 + x_t/100)(1 + x_{t-1}/100)(1 + x_{t-2}/100))^4 - 1]
```

### Ajuste sazonal (SA) via STL

Para **headline e núcleos**, calculamos uma série dessazonalizada com **STL**
(`statsmodels.tsa.seasonal.STL`, decomposição aditiva, `period=12`, `robust=True`). A m/m
já é uma taxa aditiva, então o ajuste sazonal aditivo é o modelo correto, e `robust=True`
impede que o choque de 2020–22 distorça os fatores sazonais. O resultado é determinístico
dada a entrada (auditável).

```text
mom_sa = observado − componente_sazonal(STL)     # m/m com ajuste sazonal
annualized_3m_sa = 100 * [((1 + s_t/100)(1 + s_{t-1}/100)(1 + s_{t-2}/100))^4 - 1]
                                                 # s = mom_sa; agora "SAAR" é legítimo
```

**Caveat (importante).** O fator sazonal do mês mais recente é uma **estimativa que revisa**
quando entram novos dados — leia o `annualized_3m_sa` da ponta como provisório. É um ajuste
**próprio via STL**, não o X-13ARIMA-SEATS oficial nem um número do IBGE/BCB.

**Operacional.** O STL roda só no **build-time** (pipeline) e é persistido em parquet; o app
apenas lê parquet. Por isso `statsmodels` vive no extra de build (`pipeline`/`dev`) e **não**
no `requirements.txt` do deploy. Se a dependência faltar, a série SA fica vazia (NaN) e o
painel NSA continua correto — o pipeline nunca quebra por causa do ajuste sazonal.

### Média dos núcleos

A média é calculada sobre o conjunto selecionado em `config/core_sets.yaml`. O preset default é `bcb_compact`: EX0, EX3, MS, DP e P55.

### Percentis e z-score

O percentil histórico (`percentile_since_2012`) é calculado de forma expansiva (midrank), com mínimo de 24 observações, sobre a série SGS coletada **desde 2012-01** — é essa janela longa que dá sentido a "onde o mês atual está vs. a história" e ao badge de regime. O z-score usa janela móvel de 60 meses, também com mínimo de 24 observações.

A decomposição por itens (SIDRA 7060) segue coletada **desde 2020-01** — a tabela não existe antes disso. A assimetria é intencional: percentis e regime usam só séries SGS (janela longa); a decomposição usa a janela disponível da SIDRA. O check `sgs_history_depth` falha o build estrito se o histórico SGS encurtar (ex.: regressão de parâmetro ou um futuro limite de janela da API).

## Alertas

As regras ficam em `config/alert_rules.yaml`. Cada regra define métrica, condição, threshold, severidade e mensagem. A primeira versão registra alertas ativos no último processamento.

## Validacoes

O pipeline gera `outputs/validation_report.csv` com:

- duplicidade por série e mês;
- disponibilidade das séries SGS;
- difusão entre 0 e 100;
- disponibilidade do preset default de núcleos;
- pesos não negativos;
- diferença entre soma das contribuições por grupo e IPCA mensal.

Atualizações com diferença acima de 0,05 p.p. ficam marcadas como bloqueantes no relatório.

## Auditoria de acurácia

A auditoria econométrica é executada separadamente do dashboard:

```bash
python -m ipca_dashboard.audit --start-sgs 2012-01 --start-sidra 2020-01
```

Ela refaz uma amostra longa para checar:

- cobertura temporal por série e nível SIDRA;
- IPCA mensal SGS contra headline SIDRA;
- IPCA 12m calculado contra a variável oficial SIDRA de 12 meses;
- soma das contribuições mensais por grupo;
- recomposição 12m pela contribuição encadeada;
- janela efetiva de percentis, z-score, MM3M, 12m e 3m anualizado (NSA);
- sensibilidade dos alertas em amostras `full_sample`, `since_2020` e `rolling_60m`.

Os relatórios ficam em `outputs/audit/` e não substituem os Parquets usados pela interface.

## Limitacoes metodologicas

- A decomposição granular depende da estrutura SIDRA 7060, iniciada em 2020 para a estrutura atual do IPCA.
- A contribuição 12m encadeada é uma aproximação técnica baseada no índice headline reconstruído.
- Percentis expansivos sao sensiveis ao periodo inicial escolhido; a base pública coleta SGS desde 2012-01 (pós-crise de 2008, regime de metas maduro), e essa escolha está exposta aqui em vez de embutida.
- O sistema realiza ajuste sazonal próprio via STL para headline e núcleos, com
  caveat de revisão na cauda; não realiza modelos preditivos no MVP.
