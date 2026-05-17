# SPEC — Dashboard Macro de IPCA: decomposição, difusão, núcleos e alertas

**Projeto:** Monitor de IPCA para research macro  
**Versão:** 1.0  
**Idioma:** PT-BR  
**Data:** 2026-05-17  
**Objetivo:** especificar um dashboard de baixíssimo custo técnico, alto impacto visual e linguagem de research macro para acompanhar composição do IPCA, inflação subjacente, difusão e alertas automáticos.

---

## 1. Resumo executivo

Construir um dashboard que acompanhe o IPCA de forma comparável ao que o Banco Central do Brasil costuma apresentar em suas publicações de política monetária, mas com uma camada adicional de produto: visual limpo, decomposição intuitiva, ranking de pressões, núcleos em janelas relevantes para Copom, monitor de difusão e alertas automáticos quando a inflação subjacente se deteriora.

O produto deve responder rapidamente às perguntas que uma equipe de macro research faz no dia da divulgação:

1. **O headline veio de onde?**  
   Quais grupos, itens ou subitens explicaram a variação mensal e acumulada em 12 meses?

2. **A inflação está localizada ou disseminada?**  
   O índice de difusão subiu, caiu ou está em patamar historicamente elevado?

3. **Os núcleos estão benignos ou pressionados?**  
   Núcleos em 12 meses e em 3 meses anualizados indicam convergência ou persistência?

4. **A composição é compatível com desinflação sustentável?**  
   A desaceleração vem de voláteis/administrados ou de serviços, industriais e núcleos?

5. **Há algum alerta relevante para cenário, Copom ou relatório?**  
   Exemplo: média dos núcleos acima de 5,0% em 3m saar, difusão acima do p80 histórico, serviços acelerando.

---

## 2. Posicionamento do produto

> Um monitor de inflação subjacente e composição do IPCA, com granularidade de research macro, visual limpo de relatório institucional e alertas automáticos para detectar deterioração de núcleos, difusão e composição antes que o headline conte a história inteira.

### 2.1 Valor para o usuário

| Usuário | Dor | Valor entregue |
|---|---|---|
| Economista-chefe | Precisa de leitura rápida pós-divulgação | Diagnóstico automático e gráficos prontos |
| Analista macro | Precisa auditar composição e núcleos | Dados tratados, decomposição e validações |
| Estrategista de mercado | Precisa traduzir inflação em cenário de juros | Alertas, núcleos, difusão e serviços |
| Gestor ou comitê | Precisa entender risco inflacionário sem planilha | Cockpit visual com semáforos e narrativa |
| Área de risco soberano | Precisa monitorar persistência inflacionária e reação de política monetária | Indicadores de regime e sinais de deterioração |

### 2.2 Princípios de design

1. **Baixo atrito:** abrir o dashboard e entender a mensagem em menos de 30 segundos.
2. **Rigor econométrico suficiente:** cálculos simples, auditáveis e robustos.
3. **Visual publicável:** gráficos adequados para nota, apresentação ou reunião de comitê.
4. **Reprodutibilidade:** toda métrica deve ter fonte, fórmula e tolerância.
5. **Modularidade:** núcleos, thresholds e taxonomias devem ser configuráveis.
6. **Linguagem de mesa:** foco em headline, composição, difusão, persistência, 3m saar, base effect, serviços, administrados e núcleos.

---

## 3. Escopo funcional

### 3.1 Módulo A — Painel executivo

Tela inicial em formato de **macro cockpit**.

#### Cards principais

| Card | Métrica | Unidade | Frequência |
|---|---:|---:|---|
| IPCA mensal | variação m/m | % | mensal |
| IPCA 12m | acumulado em 12 meses | % | mensal |
| IPCA 3m saar | três meses anualizado | % a.a. | mensal |
| Média dos núcleos | m/m, 12m e 3m saar | % | mensal |
| Difusão | mensal e MM3M | % de subitens | mensal |
| Alertas ativos | contagem por severidade | n | pós-divulgação |
| Principal contribuição altista | grupo/item | p.p. | mensal |
| Principal contribuição baixista | grupo/item | p.p. | mensal |

#### Objetivo da tela

Gerar uma leitura como:

> “Headline moderado, mas composição pior: serviços e núcleos aceleram, difusão segue acima do p80 e a queda em bens industriais não é suficiente para caracterizar desinflação ampla.”

---

### 3.2 Módulo B — Decomposição do IPCA

A decomposição deve operar em duas taxonomias.

#### Taxonomia 1 — Grupos IBGE do IPCA

1. Alimentação e bebidas
2. Habitação
3. Artigos de residência
4. Vestuário
5. Transportes
6. Saúde e cuidados pessoais
7. Despesas pessoais
8. Educação
9. Comunicação

#### Taxonomia 2 — Agregações macro/BCB

1. Livres
2. Administrados
3. Serviços
4. Bens industriais
5. Alimentação no domicílio
6. Comercializáveis
7. Não comercializáveis
8. Bens duráveis
9. Bens semiduráveis
10. Bens não duráveis
11. EX3 Serviços
12. EX3 Industriais

#### Visuais obrigatórios

| Visual | Descrição | Interpretação |
|---|---|---|
| Stacked bar mensal | contribuição em p.p. por grupo para o IPCA do mês | “quem explicou o mês” |
| Stacked bar 12m | contribuição acumulada por grupo para o IPCA em 12m | “quem explica o acumulado” |
| Waterfall do mês | headline decomposto em blocos principais | leitura executiva |
| Ranking de contribuição | top 10 pressões altistas e top 10 baixistas | microdrivers |
| Heatmap grupo × mês | contribuição mensal nos últimos 24 meses | persistência e rotação |
| Small multiples | inflação m/m ou 12m por grupo | comparação visual limpa |
| Treemap opcional | contribuição por item/subitem | exploração granular |

#### Requisito analítico

O usuário deve conseguir alternar o nível de agregação:

```text
headline → grupo → subgrupo → item → subitem
```

E deve poder responder:

```text
Qual foi a contribuição de alimentação no domicílio para o IPCA do mês?
Quanto transportes explica do IPCA 12m?
Quais subitens mais pressionaram o índice?
A surpresa veio de administrados ou de livres?
```

---

### 3.3 Módulo C — Monitor de núcleos

O dashboard deve tratar núcleos como uma família de medidas de inflação subjacente, não como uma métrica única. O modelo de dados precisa ser extensível, pois a lista de núcleos monitorados pode variar por publicação, preferência do usuário ou alteração metodológica.

#### Presets de núcleos

##### Preset 1 — “BCB/RPM compacto”

Conjunto usado como default para leitura executiva:

```text
EX0, EX3, MS, DP, P55
```

##### Preset 2 — “Seis núcleos”

Conjunto alinhado ao pedido inicial do projeto, parametrizável:

```text
EX0, EX1, EX2, EX3, DP, MS
```

##### Preset 3 — “Conjunto amplo SGS”

Conjunto completo para análise técnica:

```text
EX-FE, EX0, EX1, EX2, EX3, MA, MS, DP, P55
```

##### Preset 4 — “Usuário”

Conjunto livre definido em arquivo de configuração:

```yaml
core_set_user:
  - EX0
  - EX3
  - DP
  - P55
```

#### Métricas para cada núcleo

| Métrica | Fórmula/conceito | Uso |
|---|---|---|
| m/m | variação mensal | leitura da divulgação |
| 12m | acumulado em 12 meses | comparação com meta e histórico |
| 3m saar | variação de três meses anualizada | momentum |
| MM3M | média móvel de três meses | suavização simples |
| z-score histórico | distância em desvios-padrão | detecção de regime |
| percentil histórico | posição na distribuição | semáforo intuitivo |

#### Visuais obrigatórios

| Visual | Descrição |
|---|---|
| Linha 12m | IPCA cheio vs núcleos selecionados |
| Linha 3m saar | núcleos em janela curta anualizada |
| Fan chart simples | faixa mínima/máxima e média dos núcleos |
| Boxplot histórico | último dado contra distribuição histórica |
| Heatmap núcleo × mês | aceleração/desaceleração recente |
| Gap headline-core | diferença entre IPCA cheio e média dos núcleos |
| Semáforo de regime | benigno, neutro, pressionado, crítico |

#### Interpretação automática

```text
Se média dos núcleos 3m saar > média dos núcleos 12m:
    sinal = "núcleos acelerando"

Se média dos núcleos 3m saar < média dos núcleos 12m:
    sinal = "núcleos desacelerando"

Se dispersão entre núcleos aumenta:
    sinal = "leitura subjacente menos consensual"

Se EX3 Serviços acelera e difusão sobe:
    sinal = "pressão persistente em serviços"
```

---

### 3.4 Módulo D — Monitor de difusão

O índice de difusão deve ser interpretado como medida de disseminação da inflação. Ele ajuda a separar choque localizado de pressão ampla.

#### Métricas

| Métrica | Definição |
|---|---|
| Difusão mensal | percentual de subitens com variação positiva no mês |
| Difusão MM3M | média móvel de três meses |
| Difusão MM6M | média móvel de seis meses, opcional |
| Difusão z-score | desvio ante média histórica dividido pelo desvio-padrão |
| Difusão percentil | posição na distribuição histórica |
| Difusão por grupo | percentual de subitens positivos dentro de cada grupo |
| Difusão persistente | percentual de subitens com alta em 3 de 3 meses ou 4 de 6 meses |

#### Visuais obrigatórios

| Visual | Descrição |
|---|---|
| Linha histórica | difusão mensal, MM3M e bandas históricas |
| Bandas percentílicas | p20, p50, p80, p90 |
| Heatmap por grupo | grupo × mês: percentual de subitens positivos |
| Dispersão IPCA × difusão | quadrantes de diagnóstico |
| Difusão por grupo | barras horizontais ordenadas |

#### Matriz de diagnóstico IPCA × difusão

| IPCA | Difusão | Diagnóstico |
|---|---|---|
| acelera | sobe | pressão inflacionária disseminada |
| acelera | cai | choque concentrado em poucos itens |
| desacelera | sobe | headline melhora, composição piora |
| desacelera | cai | desinflação ampla |

Pseudo-regra:

```python
if ipca_mom > ipca_mom_ma3 and diffusion_mm3 > diffusion_p80:
    diagnosis = "Pressão disseminada: headline acelera com difusão elevada."
elif ipca_mom > ipca_mom_ma3 and diffusion_mm3 < diffusion_p50:
    diagnosis = "Choque localizado: headline acelera, mas difusão não confirma."
elif ipca_mom < ipca_mom_ma3 and diffusion_mm3 > diffusion_p80:
    diagnosis = "Desinflação frágil: headline melhora, mas composição continua ruim."
else:
    diagnosis = "Desinflação mais ampla ou ambiente benigno."
```

---

### 3.5 Módulo E — Alertas automáticos

Alertas devem ser definidos de forma declarativa, em YAML, para que o usuário altere thresholds sem mexer no código.

#### Estrutura de regra

```yaml
id: core_mean_3m_saar_high
metric: core_mean_3m_saar
condition: ">"
threshold: 5.0
severity: high
window: latest
cooldown_days: 30
message: "Média dos núcleos em 3m saar acima de 5,0%. Pressão subjacente incompatível com convergência confortável."
```

#### Campos obrigatórios

| Campo | Descrição |
|---|---|
| id | identificador único |
| metric | métrica monitorada |
| condition | `>`, `<`, `>=`, `<=`, `between`, `outside_band` |
| threshold | limite numérico ou intervalo |
| severity | info, medium, high, critical |
| window | latest, 3m, 6m, 12m |
| cooldown_days | dias mínimos antes de repetir alerta |
| message | mensagem legível |

#### Alertas macro recomendados

| Alerta | Regra sugerida | Severidade | Interpretação |
|---|---:|---|---|
| Núcleos pressionados | média dos núcleos 3m saar > 5,0% | high | pressão subjacente desconfortável |
| Núcleo crítico | qualquer núcleo 3m saar > 6,5% | critical | risco de persistência |
| Difusão elevada | difusão MM3M > p80 histórico | high | inflação disseminada |
| Difusão crítica | difusão MM3M > p90 histórico | critical | deterioração ampla |
| Serviços acelerando | serviços 3m saar > serviços 12m | high | componente inercial piorando |
| Administrados dominando | contribuição administrados > 40% do IPCA mensal | medium | choque regulado/tarifário |
| Alimentação dominando | alimentação domicílio > 35% do IPCA mensal | medium | choque de alimentos |
| Headline benigno, núcleo ruim | IPCA 12m cai e média dos núcleos 3m saar sobe | high | desinflação frágil |
| Choque localizado | IPCA mensal > p80 e difusão < p50 | medium | pressão concentrada |
| Desinflação ampla | IPCA mensal < p40 e difusão < p40 | info | composição benigna |

---

## 4. Fontes de dados

### 4.1 IBGE/SIDRA

Fonte primária para IPCA, pesos, variações por grupo, subgrupo, item e subitem.

#### Uso no projeto

1. Coletar variação mensal por nível hierárquico.
2. Coletar peso mensal por nível hierárquico.
3. Calcular contribuição mensal ao headline.
4. Reproduzir ranking de pressões por item/subitem.
5. Calcular difusão própria por subitem, se desejado.
6. Auditar decomposição contra IPCA headline.

#### Tabelas e endpoints

| Recurso | Uso |
|---|---|
| SIDRA tabela 7060 | IPCA por grupos, subgrupos, itens e subitens |
| Variável: variação mensal | cálculo de inflação m/m |
| Variável: variação acumulada em 12 meses | validação e comparação |
| Variável: peso mensal | cálculo de contribuição |
| Localidade: Brasil | dashboard nacional |

Exemplo conceitual de endpoint SIDRA:

```text
https://apisidra.ibge.gov.br/values/t/7060/n1/1/v/{VARIAVEL}/p/all/c315/all
```

> Observação: na implementação, os códigos de variável devem ser confirmados via metadados da tabela 7060. O pipeline deve guardar o mapeamento em `config/sidra_7060.yaml`.

---

### 4.2 BCB/SGS

Fonte primária para séries analíticas derivadas do IPCA, núcleos de inflação, agregações macro e índice de difusão.

#### Endpoint padrão

```text
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODIGO}/dados?formato=json
```

Com datas:

```text
https://api.bcb.gov.br/dados/serie/bcdata.sgs.{CODIGO}/dados?formato=json&dataInicial=01/01/2012&dataFinal=31/12/2026
```

#### Séries recomendadas

| Série | Código SGS | Grupo no dashboard |
|---|---:|---|
| IPCA mensal | 433 | headline |
| Administrados | 4449 | agregação macro |
| Livres | 11428 | agregação macro |
| Alimentação no domicílio | 27864 | agregação macro |
| Serviços | 10844 | agregação macro |
| Bens industriais | 27863 | agregação macro |
| Comercializáveis | 4447 | agregação macro |
| Não comercializáveis | 4448 | agregação macro |
| Bens não duráveis | 10841 | agregação macro |
| Bens semiduráveis | 10842 | agregação macro |
| Bens duráveis | 10843 | agregação macro |
| Núcleo EX-FE | 28751 | núcleo |
| Núcleo EX0 | 11427 | núcleo |
| Núcleo EX1 | 16121 | núcleo |
| Núcleo EX2 | 27838 | núcleo |
| Núcleo EX3 | 27839 | núcleo |
| Núcleo DP | 16122 | núcleo |
| Núcleo MA | 11426 | núcleo |
| Núcleo MS | 4466 | núcleo |
| Núcleo P55 | 28750 | núcleo |
| Difusão | 21379 | difusão |
| EX3 Serviços | 29683 | serviços subjacente |
| EX3 Industriais | 29684 | industriais núcleo |

---

## 5. Metodologia quantitativa

### 5.1 Contribuição mensal

Para cada item `i` no mês `t`:

```text
contrib_i,t = peso_i,t × variacao_i,t / 100
```

Onde:

```text
peso_i,t       = peso mensal do item no IPCA, em %
variacao_i,t   = variação mensal do item, em %
contrib_i,t    = contribuição ao IPCA, em pontos percentuais
```

Checagem:

```text
sum_i(contrib_i,t) ≈ IPCA_t
```

Tolerância recomendada:

```text
abs(sum_contrib_t - IPCA_t) <= 0,02 p.p.
```

Motivos possíveis para pequenas diferenças:

1. Arredondamento de variações e pesos.
2. Uso de pesos divulgados já arredondados.
3. Hierarquia de agregação.
4. Alterações metodológicas ou correções pontuais.

---

### 5.2 Contribuição acumulada em 12 meses

Oferecer dois métodos.

#### Método A — soma simples das contribuições mensais

```text
contrib_12m_simple_i,t = Σ contrib_i,s, para s = t-11,...,t
```

Vantagem: simples e intuitivo.  
Limitação: pode não recompor perfeitamente o IPCA 12m por causa do encadeamento do índice e da variação dos pesos.

#### Método B — contribuição encadeada

Recomendado como default técnico.

```text
contrib_12m_chain_i,t = Σ [(I_{s-1} / I_{t-12}) × contrib_i,s], para s = t-11,...,t
```

Onde:

```text
I_t = número-índice do IPCA no mês t
```

Checagem:

```text
sum_i(contrib_12m_chain_i,t) ≈ IPCA_12m_t
```

---

### 5.3 Variação 3m saar

A métrica de três meses anualizada é central para leitura de momentum.

```text
x_3m_saar_t = 100 × [((1 + x_t/100) × (1 + x_{t-1}/100) × (1 + x_{t-2}/100))^4 - 1]
```

Aplicar a:

```text
IPCA headline
livres
administrados
serviços
bens industriais
alimentação no domicílio
EX3 Serviços
EX3 Industriais
cada núcleo
média dos núcleos
```

---

### 5.4 Média dos núcleos

A média dos núcleos deve ser calculada a partir de um conjunto selecionado em configuração.

```yaml
core_set_default:
  - EX0
  - EX3
  - MS
  - DP
  - P55
```

Fórmula:

```text
core_mean_mom_t = mean(core_mom_j,t), para j ∈ core_set
```

Depois encadear para obter:

```text
core_mean_12m_t
core_mean_3m_saar_t
core_mean_mm3m_t
```

---

### 5.5 Difusão própria por subitem

Caso o dashboard calcule uma difusão alternativa usando SIDRA:

```text
diffusion_t = 100 × count(subitem_mom_i,t > 0) / count(subitem_i,t válido)
```

Versões opcionais:

```text
diffusion_weighted_t = 100 × Σ peso_i,t × 1(subitem_mom_i,t > 0) / Σ peso_i,t

persistent_diffusion_3m_t = 100 × count(subitem com alta em 3 dos últimos 3 meses) / count(subitem válido)

persistent_diffusion_6m_t = 100 × count(subitem com alta em pelo menos 4 dos últimos 6 meses) / count(subitem válido)
```

Observação: a versão oficial do BCB deve continuar sendo a referência do dashboard; a versão própria deve ser rotulada como “difusão calculada”.

---

### 5.6 Z-score e percentis

Para cada série relevante:

```text
z_t = (x_t - mean(x_window)) / std(x_window)
```

Janelas sugeridas:

```text
2004-presente
2012-presente
2017-2019 pré-pandemia
2020-presente
janela móvel de 60 meses
```

Classificação sugerida:

| Percentil | Classificação |
|---:|---|
| < p20 | benigno |
| p20 a p60 | normal |
| p60 a p80 | atenção |
| p80 a p90 | pressionado |
| > p90 | crítico |

---

## 6. Diagnóstico automático

### 6.1 Template narrativo pós-divulgação

```text
O IPCA de {mes_ref} veio em {ipca_mom:.2f}%, acumulando {ipca_12m:.2f}% em 12 meses.
A composição foi {avaliacao_composicao}, com destaque altista para {top_positive_group}
e contribuição baixista de {top_negative_group}.

A média dos núcleos avançou {core_mean_mom:.2f}% no mês e roda a {core_mean_3m_saar:.2f}%
em 3m anualizado, sinalizando {avaliacao_nucleos}. A difusão ficou em {diffusion:.1f}%
({diffusion_mm3m:.1f}% em MM3M), {avaliacao_difusao}.

Leitura: {headline_assessment}. {core_assessment}. {monetary_policy_risk}.
```

### 6.2 Exemplo de saída

```text
O IPCA de abril veio em 0,38%, acumulando 4,20% em 12 meses. A composição foi moderadamente adversa, com destaque altista para alimentação no domicílio e contribuição baixista de bens industriais.

A média dos núcleos avançou 0,41% no mês e roda a 5,30% em 3m anualizado, sugerindo pressão subjacente ainda acima do conforto. A difusão ficou em 63,5% em MM3M, acima do p80 histórico.

Leitura: o headline não é explosivo, mas a composição segue ruim. O risco relevante é persistência em serviços e núcleos, não apenas choque pontual de administrados ou alimentos.
```

### 6.3 Motor de frases

Mapear regras para mensagens:

```yaml
composition_bad:
  condition: "core_mean_3m_saar > 5 and diffusion_mm3 > diffusion_p80"
  text: "composição adversa, com pressão subjacente e disseminação elevadas"

composition_localized_shock:
  condition: "ipca_mom > ipca_p80 and diffusion_mm3 < diffusion_p50"
  text: "alta concentrada em poucos componentes, sem disseminação equivalente"

services_persistent:
  condition: "services_3m_saar > services_12m and ex3_services_3m_saar > ex3_services_12m"
  text: "serviços mostram aceleração, reforçando risco de persistência"
```

---

## 7. Arquitetura técnica

### 7.1 Stack recomendada para MVP

| Camada | Ferramenta recomendada | Justificativa |
|---|---|---|
| Ingestão | Python + requests | simples e robusto |
| Tratamento | pandas + numpy | padrão para séries macro |
| Validação | pandera ou pydantic | data quality auditável |
| Armazenamento | Parquet | rápido, leve, barato |
| Dashboard | Streamlit | menor custo técnico |
| Gráficos | Plotly | interativo e exportável |
| Configuração | YAML | fácil de ajustar thresholds e séries |
| Agendamento | GitHub Actions ou cron | custo quase zero |
| Alertas | Telegram, Slack webhook ou e-mail | implementação rápida |
| Deploy | Streamlit Community Cloud, Render, Railway ou VPS | barato e simples |

Recomendação pragmática:

```text
Streamlit + Plotly + Parquet + GitHub Actions
```

### 7.2 Pipeline

```text
1. fetch_ibge_sidra()
   - baixa IPCA por grupo, subgrupo, item, subitem e pesos

2. fetch_bcb_sgs()
   - baixa IPCA, agregações macro, núcleos e difusão

3. normalize_dates()
   - padroniza datas para YYYY-MM

4. build_ipca_hierarchy()
   - monta árvore headline > grupo > subgrupo > item > subitem

5. calculate_contributions()
   - calcula contribuição mensal e 12m

6. calculate_transforms()
   - 12m, 3m saar, MM3M, z-score e percentis

7. validate_data()
   - reconciliação, missing, duplicidades e outliers

8. generate_alerts()
   - aplica regras declarativas

9. write_processed_data()
   - salva parquet/csv para o dashboard

10. render_dashboard()
   - carrega dados finais sem recalcular tudo na UI
```

### 7.3 Frequência de atualização

| Evento | Ação |
|---|---|
| Diariamente às 8h | checar se há dados novos no IBGE/BCB |
| Dia provável de IPCA | rodar coleta a cada 30 minutos entre 8h e 12h |
| Após novo dado | recalcular métricas, gerar alertas e atualizar dashboard |
| Após erro de validação | logar falha e bloquear atualização pública |

---

## 8. Modelo de dados

### 8.1 Tabela `ipca_items_monthly`

```text
date: date
source: string              # IBGE/SIDRA
item_code: string
item_name: string
level: string               # headline, group, subgroup, item, subitem
parent_code: string
group_code: string
group_name: string
weight: float               # %
mom: float                  # %
ytd: float                  # %
yoy: float                  # %
index_number: float         # opcional
contribution_mom: float     # p.p.
contribution_12m_simple: float
contribution_12m_chain: float
```

### 8.2 Tabela `bcb_series_monthly`

```text
date: date
source: string              # BCB/SGS
sgs_code: int
series_name: string
series_short_name: string
series_group: string        # headline, aggregate, core, diffusion
mom: float                  # % mensal ou % difusão
rolling_12m: float
three_month_saar: float
moving_average_3m: float
moving_average_6m: float
zscore_60m: float
percentile_since_2012: float
```

### 8.3 Tabela `core_metrics_monthly`

```text
date: date
core_set_name: string
core_name: string
mom: float
rolling_12m: float
three_month_saar: float
zscore_60m: float
percentile_since_2012: float
```

### 8.4 Tabela `alerts`

```text
date: date
reference_month: string
alert_id: string
metric: string
value: float
threshold: float
condition: string
severity: string
message: string
status: string              # new, repeated, resolved
created_at: datetime
```

### 8.5 Tabela `release_calendar`

```text
reference_month: string
expected_release_date: date
actual_release_date: date
source: string
status: string              # expected, released, delayed
```

---

## 9. Configurações

### 9.1 `config/series_sgs.yaml`

```yaml
series:
  headline:
    IPCA:
      code: 433
      unit: pct_mom

  aggregates:
    Administrados:
      code: 4449
    Livres:
      code: 11428
    Alimentacao_no_domicilio:
      code: 27864
    Servicos:
      code: 10844
    Bens_industriais:
      code: 27863
    Comercializaveis:
      code: 4447
    Nao_comercializaveis:
      code: 4448
    Bens_nao_duraveis:
      code: 10841
    Bens_semiduraveis:
      code: 10842
    Bens_duraveis:
      code: 10843

  cores:
    EX_FE:
      code: 28751
    EX0:
      code: 11427
    EX1:
      code: 16121
    EX2:
      code: 27838
    EX3:
      code: 27839
    DP:
      code: 16122
    MA:
      code: 11426
    MS:
      code: 4466
    P55:
      code: 28750

  diffusion:
    Difusao:
      code: 21379

  underlying:
    EX3_Servicos:
      code: 29683
    EX3_Industriais:
      code: 29684
```

### 9.2 `config/core_sets.yaml`

```yaml
core_sets:
  bcb_compact:
    label: "BCB/RPM compacto"
    members: [EX0, EX3, MS, DP, P55]

  six_cores:
    label: "Seis núcleos"
    members: [EX0, EX1, EX2, EX3, DP, MS]

  broad_sgs:
    label: "Conjunto amplo SGS"
    members: [EX_FE, EX0, EX1, EX2, EX3, MA, MS, DP, P55]
```

### 9.3 `config/alert_rules.yaml`

```yaml
rules:
  - id: core_mean_3m_saar_high
    metric: core_mean_3m_saar
    condition: ">"
    threshold: 5.0
    severity: high
    cooldown_days: 30
    message: "Média dos núcleos em 3m saar acima de 5,0%. Pressão subjacente desconfortável."

  - id: diffusion_mm3_p80
    metric: diffusion_mm3_percentile
    condition: ">"
    threshold: 80
    severity: high
    cooldown_days: 30
    message: "Difusão MM3M acima do p80 histórico. Inflação disseminada."

  - id: services_accelerating
    metric: services_3m_saar_minus_services_12m
    condition: ">"
    threshold: 0
    severity: high
    cooldown_days: 30
    message: "Serviços em 3m saar acima do ritmo de 12 meses. Sinal de aceleração."

  - id: localized_shock
    metric: localized_shock_score
    condition: ">"
    threshold: 1
    severity: medium
    cooldown_days: 30
    message: "Headline pressionado com difusão baixa. Alta possivelmente concentrada."
```

---

## 10. UX e design visual

### 10.1 Layout proposto

```text
[Header]
IPCA Macro Dashboard | último dado | data de atualização | fontes

[Cards]
IPCA m/m | IPCA 12m | IPCA 3m saar | média núcleos 3m saar | difusão MM3M | alertas

[Seção 1 — Decomposição]
Stacked bar mensal | waterfall | ranking de contribuições

[Seção 2 — Núcleos]
IPCA vs núcleos 12m | núcleos 3m saar | fan chart | semáforo

[Seção 3 — Difusão]
Linha histórica | bandas percentílicas | heatmap por grupo | quadrantes IPCA × difusão

[Seção 4 — Diagnóstico]
Texto automático pós-divulgação + alertas ativos

[Seção 5 — Auditoria]
Fontes | tolerâncias | validações | download CSV/PNG
```

### 10.2 Paleta visual

Manter paleta sóbria, institucional e consistente.

| Família | Uso visual |
|---|---|
| Headline | destaque neutro |
| Alimentação | cor quente moderada |
| Serviços | cor forte/alerta |
| Industriais | cor fria |
| Administrados | cor distinta de choque regulado |
| Núcleos | tons coordenados, sem excesso |
| Difusão | linha e bandas discretas |
| Alertas | semáforo: info, medium, high, critical |

### 10.3 Regras de visualização

1. Sempre mostrar unidade no título ou eixo: `%`, `p.p.`, `3m saar`, `12m`, `MM3M`.
2. Sempre destacar o último ponto.
3. Evitar excesso de labels em séries longas.
4. Usar anotações curtas nos pontos-chave.
5. Exibir fonte e data de coleta no rodapé.
6. Permitir exportação de PNG em todos os gráficos principais.
7. Evitar “dashboard poluído”; priorizar leitura executiva.

---

## 11. Validação e qualidade dos dados

### 11.1 Checagens obrigatórias

| Teste | Critério |
|---|---|
| Soma de contribuições | diferença vs IPCA mensal menor que 0,02 p.p. |
| Missing em série BCB | nenhum missing após início oficial da série |
| Duplicidade | uma observação por série por mês |
| Datas futuras | proibidas, exceto calendário de divulgação |
| Peso mensal | peso deve ser não negativo e coerente com o nível |
| Difusão | valor entre 0 e 100 |
| Núcleos | variação mensal plausível dentro de bandas históricas ou flagged |
| Divergência BCB/SIDRA | alertar se diferença persistente acima da tolerância |
| Versão de dados | salvar timestamp da coleta |

### 11.2 Testes unitários

```text
test_contribution_sum_matches_headline()
test_12m_chain_contribution_recomposes_headline()
test_core_mean_uses_selected_core_set()
test_three_month_saar_formula()
test_diffusion_between_0_and_100()
test_no_duplicate_dates_per_series()
test_alert_triggers_when_threshold_crossed()
test_alert_does_not_repeat_during_cooldown()
test_processed_data_has_latest_reference_month()
```

### 11.3 Critério de bloqueio

O dashboard não deve publicar uma atualização nova se:

```text
abs(sum_contrib_t - ipca_t) > 0,05 p.p.
```

ou se houver:

```text
missing em headline
missing em peso mensal de grupo
missing em núcleo selecionado para core_mean
```

Nesse caso, exibir banner:

```text
Atualização bloqueada por validação. Último dado validado: {last_valid_month}.
```

---

## 12. MVP

### 12.1 Entregáveis do MVP

1. Coleta automática de SGS para IPCA, agregações macro, núcleos e difusão.
2. Coleta de SIDRA 7060 para grupos, itens/subitens e pesos.
3. Decomposição mensal por grupos IBGE.
4. Ranking de top pressões altistas e baixistas.
5. Painel de núcleos em m/m, 12m e 3m saar.
6. Média dos núcleos configurável.
7. Monitor de difusão com MM3M, percentis e z-score.
8. Alertas em YAML.
9. Diagnóstico automático em texto.
10. Exportação CSV e PNG.
11. Página de metodologia.
12. Data quality checks básicos.

### 12.2 Não escopo do MVP

1. Nowcast de IPCA.
2. Dessazonalização X-13 completa.
3. Modelos preditivos sofisticados.
4. Integração paga com terminal ou base proprietária.
5. Relatório PDF totalmente automatizado.
6. Backtest econométrico de capacidade preditiva dos núcleos.

---

## 13. Backlog avançado

| Feature | Ganho |
|---|---|
| Dessazonalização via X-13/STL | leitura mais precisa de momentum |
| Comparação com Focus/consenso | mensurar surpresa inflacionária |
| Nowcast IPCA | antecipar divulgação oficial |
| Relatório PDF pós-divulgação | produto institucional pronto |
| Integração Telegram/Slack | alertas push automáticos |
| Monitor de serviços subjacentes | foco no componente mais relevante para BC |
| Forecast de núcleos | cenário curto via ARIMA/ETS/ML |
| Comparação internacional | inflação subjacente Brasil vs peers |
| Decomposição Shapley-like | atribuição 12m mais sofisticada |
| Painel Copom | conectar inflação, expectativas, hiato e Selic |

---

## 14. Estrutura do repositório

```text
/ipca-dashboard
  /config
    series_sgs.yaml
    sidra_7060.yaml
    core_sets.yaml
    alert_rules.yaml
    chart_theme.yaml

  /data
    /raw
      /ibge
      /bcb
    /processed
      ipca_items_monthly.parquet
      bcb_series_monthly.parquet
      core_metrics_monthly.parquet
      alerts.parquet

  /src
    __init__.py
    fetch_ibge.py
    fetch_bcb.py
    transform_dates.py
    transform_contributions.py
    transform_cores.py
    transform_diffusion.py
    transform_alerts.py
    validation.py
    diagnostics.py
    io.py

  /dashboard
    app.py
    /pages
      01_Executive.py
      02_Decomposition.py
      03_Cores.py
      04_Diffusion.py
      05_Alerts.py
      06_Methodology.py

  /notebooks
    00_data_audit.ipynb
    01_prototype_charts.ipynb

  /tests
    test_fetch_bcb.py
    test_fetch_ibge.py
    test_contributions.py
    test_cores.py
    test_diffusion.py
    test_alerts.py

  README.md
  methodology.md
  requirements.txt
  pyproject.toml
```

---

## 15. Pseudocódigo crítico

### 15.1 Coleta SGS

```python
import requests
import pandas as pd


def fetch_sgs(code: int, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    base = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
    params = {"formato": "json"}
    if start:
        params["dataInicial"] = start
    if end:
        params["dataFinal"] = end

    response = requests.get(base, params=params, timeout=30)
    response.raise_for_status()

    df = pd.DataFrame(response.json())
    df["date"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["value"] = pd.to_numeric(df["valor"].str.replace(",", "."), errors="coerce")
    return df[["date", "value"]]
```

### 15.2 Cálculo de 3m saar

```python
def calc_3m_saar(series: pd.Series) -> pd.Series:
    gross = 1 + series / 100
    return 100 * (gross.rolling(3).apply(lambda x: x.prod(), raw=True) ** 4 - 1)
```

### 15.3 Contribuição mensal

```python
def calc_contribution(weight: pd.Series, mom: pd.Series) -> pd.Series:
    return weight * mom / 100
```

### 15.4 Alertas

```python
import operator

OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


def evaluate_rule(value: float, condition: str, threshold: float) -> bool:
    if condition not in OPS:
        raise ValueError(f"Unsupported condition: {condition}")
    return OPS[condition](value, threshold)
```

---

## 16. Métricas de sucesso

| Dimensão | Meta |
|---|---|
| Precisão | decomposição mensal bate com headline dentro de 0,02 p.p. |
| Atualização | dashboard atualizado no dia da divulgação |
| Latência | coleta + tratamento em menos de 5 minutos |
| Usabilidade | leitura executiva em menos de 30 segundos |
| Visual | gráficos exportáveis para relatório |
| Robustez | alertas e validações sem falsos positivos excessivos |
| Manutenção | thresholds e séries alteráveis por YAML |
| Custo | operação viável com stack gratuita ou quase gratuita |

---

## 17. Critérios de aceite

O projeto estará aceito quando:

1. O usuário conseguir ver IPCA m/m, 12m e 3m saar na tela inicial.
2. A contribuição por grupo somar aproximadamente o headline mensal.
3. O dashboard exibir top 10 pressões altistas e baixistas por item/subitem.
4. A página de núcleos permitir selecionar presets de núcleos.
5. A média dos núcleos for recalculada corretamente conforme o preset.
6. A difusão mostrar valor mensal, MM3M, percentil e z-score.
7. Alertas forem disparados quando thresholds forem cruzados.
8. O diagnóstico automático gerar texto coerente com as métricas.
9. Todos os gráficos principais puderem ser exportados.
10. A página metodológica listar fontes, fórmulas e tolerâncias.

---

## 18. Riscos e mitigação

| Risco | Impacto | Mitigação |
|---|---|---|
| Mudança de códigos SGS | alto | manter `series_sgs.yaml` versionado e checar metadados |
| Mudança em estrutura do IPCA | alto | detectar novos códigos SIDRA e logar alterações |
| Pesos arredondados não recompõem headline | médio | tolerância explícita e comparação com headline BCB |
| Dados oficiais corrigidos posteriormente | médio | armazenar timestamp e permitir recarga completa |
| Alertas demais geram ruído | médio | cooldown e severidade por regra |
| Dashboard lento | baixo | pré-processar em Parquet |
| Visual poluído | médio | limitar gráficos por página e usar drill-down |

---

## 19. Fontes oficiais e documentação

1. IBGE — IPCA: página oficial, resultados, tabelas, informações técnicas e cobertura do índice.  
   <https://www.ibge.gov.br/estatisticas/todos-os-produtos-estatisticas/9256-indice-nacional-de-precos-ao-consumidor-amplo.html>

2. SIDRA — Sistema IBGE de Recuperação Automática.  
   <https://sidra.ibge.gov.br/>

3. BCB — API SGS/BCData.  
   <https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json>

4. BCB — Portal de Dados Abertos, exemplo da série de difusão SGS 21379.  
   <https://dadosabertos.bcb.gov.br/dataset/21379-indice-nacional-de-precos-ao-consumidor-amplo-ipca---indice-de-difusao>

5. BCB — Nota Técnica nº 57: “Núcleos de inflação e outras séries analíticas derivadas do IPCA: metodologia consolidada”.  
   <https://liftchallenge.bcb.gov.br/content/publicacoes/notastecnicas/NT_57_202512.pdf>

---

## 20. Próxima ação recomendada

Construir primeiro o MVP em Streamlit com dados BCB/SGS, porque isso entrega rapidamente o painel de núcleos, difusão e agregações macro. Em seguida, integrar SIDRA para a decomposição granular por grupo, item e subitem.

Sequência ótima:

```text
Semana 1:
  SGS + transformações + página executiva + núcleos + difusão

Semana 2:
  SIDRA + contribuições + ranking + waterfall + validação

Semana 3:
  alertas + diagnóstico automático + exportação + polimento visual
```

---

## 21. Output esperado

Um dashboard que, no dia da divulgação do IPCA, gere automaticamente:

1. **Cockpit executivo** com headline, núcleos, difusão e alertas.
2. **Decomposição visual** por grupo e agregação macro.
3. **Ranking de pressões** por item/subitem.
4. **Monitor de núcleos** em 12m e 3m saar.
5. **Monitor de difusão** com bandas históricas.
6. **Diagnóstico textual** em linguagem de research.
7. **Arquivos exportáveis** para relatório, apresentação ou call de cenário.

