# SPEC.md — OpenIPCA (V3)

**Projeto:** OpenIPCA — monitor open-source de inflação brasileira além do headline.
**Tagline:** *Brazilian inflation beyond the headline.*
**Base de código:** repo `OpenIPCA` (commit `e5a3fc5`), pacote `src/ipca_dashboard/`.
**Versão-alvo:** `v0.1.0-public`.
**Data:** 2026-05-28.
**Natureza desta versão:** a V3 substitui a V2. Ela mantém o rigor de hardening da V2, mas reorienta o documento para o objetivo real — **lançar rápido um produto macro confiável que prove, em público, ethos de economista rigoroso E de founder AI-native** — e adiciona uma arquitetura de IA **model-upgradable**: trocar por um modelo melhor é um processo testável (eval gate + guardrails), não reescrita.

---

## 0. O que mudou da V2 para a V3

Para quem vem da V2, os deltas materiais:

1. **IA reposicionada de "narrador opcional escondido" para camada de primeira classe, aterrada e agêntica.** A IA **orquestra** o núcleo determinístico (tool-use), não apenas o narra. Toda afirmação rastreia a um `evidence_id`. Ver seção 3.
2. **Nova seção: arquitetura preparada para a evolução dos modelos** (seção 3.5). O ativo durável é o contrato determinístico (Tool API + evidence schema) + um *eval harness* que transforma "trocar de modelo" em um processo testável e seguro. O app fica melhor quando o modelo fica melhor, sem reescrita.
3. **Dessazonalização entra no escopo** (seção 4.4). A V2 calculava `3m saar` sobre série bruta sem enfrentar sazonalidade. Decisão: em v0.1 **não anualizar série NSA**; em v0.2, STL.
4. **Bugs reclassificados em bloqueante × polish** (seção 5). Seis bloqueiam o lançamento; quatro vão para depois.
5. **Correção de percentil centralizada** em `transforms.py` **e** `audit.py` (a V2 só corrigia o primeiro).
6. **Escopo de lançamento enxuto.** Cinco releases viram um v0.1 focado + iteração. Governança institucional pesada (CITATION, múltiplos templates) adiada.
7. **Distribuição como feature de primeira classe** (seção 8): detecção de divulgação, fluxo release-day via PR (human-in-the-loop) **[alvo v0.2]**, artefato estático compartilhável, bilinguismo.
8. **Decisões de produto fixadas:** nome `OpenIPCA` mantido; **sem expansão para outros índices** (IGP-M, PCE etc.); disclaimer de não-afiliação ao IBGE/BCB.

---

## 1. Tese e princípios

> **OpenIPCA transforma dados oficiais do IBGE/SIDRA e do BCB/SGS em decomposição, núcleos, difusão e alertas auditáveis. Os números são determinísticos. A interpretação é orquestrada por IA aterrada na evidência. A metodologia é transparente. E a camada de IA é model-upgradable: absorve modelos melhores via evals e guardrails, sem reescrever o sistema.**

### 1.1 Princípios (decididos, não opcionais)

1. **Determinístico no núcleo.** Nenhum número macro relevante é gerado por IA. Todo número vem de função determinística do pacote ou de Parquet processado.
2. **IA orquestra, não narra.** A IA tem acesso a uma *Tool API* determinística e a uma *evidence table*; ela compõe interpretação chamando ferramentas, não recebendo um blob de texto pronto. Isso dissolve o falso trade-off "IA protagonista × IA subordinada": a IA é protagonista da **interface** e serva da **evidência**.
3. **Tudo rastreável.** Cada afirmação de IA carrega um `evidence_id` existente; sem isso, é rejeitada por guardrail.
4. **Human-in-the-loop para o que é público.** Nada gerado por IA é publicado sem revisão humana. O pipeline *propõe*; a pessoa *aprova*.
5. **Reprodutível e auditável.** Todo artefato de IA é carimbado com `model_id`, `prompt_version`, `prompt_hash`, `evidence_hash`, `schema_version`, `generated_at`.
6. **Funciona sem IA.** O produto é 100% útil com IA desligada; o brief determinístico é sempre o piso.
7. **Preparado para a evolução da IA.** A inteligência é configuração; a segurança e o aterramento são código. Trocar/atualizar modelo é um processo *eval-gated*, não um risco.
8. **Sem secrets no repo. Sem dados fictícios. Sem recomendação de investimento.**

---

## 2. Posicionamento e escopo

### 2.1 Nome e marca
- Nome público e do repo: **OpenIPCA**. Pacote Python permanece `ipca_dashboard` em v0.1; migração opcional para `openipca` só em v1.0, com alias de compatibilidade.
- **Decisão fixa: não expandir para outros índices de inflação.** O foco em IPCA é vantagem de clareza e de comunidade. Expansão futura, se houver, será projeto/nome separado.
- **Disclaimer obrigatório** (README + app): *"OpenIPCA não é afiliado ao IBGE ou ao Banco Central do Brasil. Usa dados públicos oficiais. Não é recomendação de investimento e pode conter erros."*
- Antes de brandear: checar disponibilidade de repo/org no GitHub, PyPI, domínio e handle social.

### 2.2 Fora de escopo (v0.1)
Forecast de inflação; Next.js/FastAPI; outros índices; alertas push; consenso/Focus automático; live AI na demo pública; qualquer chave versionada.

---

## 3. Arquitetura de IA (peça central)

### 3.1 Modelo mental

```
Dados oficiais ─▶ Pipeline determinístico ─▶ Tool API + Evidence Table ─▶ LLM (orquestra) ─▶ Saída aterrada ─▶ Guardrails ─▶ Revisão humana ─▶ Publicação
        (números)            (contrato estável)            (inteligência)        (verificação)        (HITL)
```

A **inteligência** (o modelo) é plugável e descartável. O **contrato** (Tool API + evidence schema + guardrails) é o ativo durável e cresce de valor conforme os modelos melhoram.

### 3.2 Contrato estável: Tool API determinística

Expor as funções determinísticas como ferramentas tipadas e documentadas, com JSON schema, em `src/ipca_dashboard/ai/tools.py`. Exemplos:

```text
get_headline(reference_month)               -> mom, 12m, 3m_accum, (3m_saar se SA disponível)
get_contributions(reference_month, level)   -> top_positive[], top_negative[]
get_cores(reference_month, core_set)        -> mean, members[], completude
get_diffusion(reference_month)              -> official, mm3, percentile
get_alerts(reference_month)                 -> ativos[]
get_series(series, start, end)              -> série temporal
```

Regras:
- Toda ferramenta retorna **valor + `evidence_id` + metadados** (fonte, data, unidade), nunca número solto.
- O schema das ferramentas é versionado. Modelos melhores usam as **mesmas** ferramentas com mais competência — sem reescrita.
- A Tool API é a fronteira: a IA só "enxerga" o mundo através dela.

### 3.3 Evidence table + grounding + guardrails

- `build_inflation_context()` e `build_evidence_table()` produzem o contexto estruturado e a tabela de evidências (cada uma com `evidence_id`, `metric`, `value`, `unit`, `date`, `source`, `interpretation`).
- **Guardrail de aterramento:** afirmação interpretativa referencia **`evidence_ids[]` (uma ou mais)**; número referencia **um** `evidence_id`; classificação de regime referencia uma `rule_id` + `evidence_ids`. Sem isso → `ValueError` e fallback determinístico. Schema mínimo: `{text, type: number|interpretation|regime, evidence_ids[]}`.
- **Guardrail de escopo:** perguntas fora de inflação brasileira são recusadas.
- **Guardrail de números:** a saída não pode introduzir número que não venha de ferramenta/evidência.
- **Guardrail de política monetária:** permitido tom cauteloso ("leitura compatível com cautela", "reduz conforto para interpretação dovish"); **proibido** prever Copom/Selic ou recomendar ativos. Schema: `monetary_policy_tone: cautious|benign|adverse|mixed`, `investment_advice: false`.
- Guardrails são **independentes de modelo** — são o piso de segurança que permanece igual de Opus 4 a "Opus N".

### 3.4 Camada provider-agnostic e modelo como configuração

```python
class LLMProvider(Protocol):
    name: str
    capabilities: set[str]  # {"text","structured","tools","reasoning"}
    def generate_structured(self, messages, schema, tools=None, *, temperature=0.0) -> dict: ...
```

Providers — **mínimo de v0.1: `NoAIProvider` + um provider hospedado** (`OpenAIProvider` ou `AnthropicProvider`). Manter o Protocol fino; multi-provider e `OllamaProvider` (LLM local) ficam para v0.2.
- `NoAIProvider` — sempre disponível, sem chave, retorna fallback determinístico, usado em CI.
- `OpenAIProvider` / `AnthropicProvider` — opcional; só inicializa com chave; nunca loga/serializa a chave.

**Modelo é config, não código** (`config/ai.yaml`): id do modelo, provider, temperatura, capability flags, custo/latência-alvo. Pin por ambiente (reprodutibilidade); upgrade é troca de uma linha **sujeita ao eval gate** (3.5).

### 3.5 Preparado para a evolução dos modelos *(novo na V3)*

O objetivo: o OpenIPCA é **model-upgradable by design** — quando surge um modelo melhor, ele é testado pelo eval gate e promovido com segurança, **sem reescrever Tool API, evidence schema ou guardrails**. A IA não melhora "magicamente sozinha"; a arquitetura é que está pronta para absorver ganhos. Mecanismos:

1. **Eval harness como portão de upgrade.** `src/ipca_dashboard/ai/evals/` com casos (`broad_disinflation`, `fragile_disinflation`, `localized_shock`, `core_pressure`, …) e esperados. Promover um modelo novo exige:
   - **100% de aterramento/guardrail** (zero claims sem `evidence_id`, zero números inventados, recusa correta de fora-de-escopo);
   - **acurácia de classificação de regime ≥ baseline**;
   - **qualidade do brief não regride** (rubrica simples pontuada, golden briefs versionados).
   Comando: `make eval-model MODEL=<id>`. Sem passar no gate, não promove.
2. **Capability tiers.** O app consulta `provider.capabilities` e habilita features por tier:
   - *no-ai* → só determinístico;
   - *local/básico* (text/structured) → brief grounded simples;
   - *frontier* (tools/reasoning) → Ask-the-IPCA agêntico multi-passo.
   Conforme modelos ganham capacidade (e barateiam), basta **flipar flags** — a arquitetura já comporta.
3. **Schema-first / structured outputs versionados** (`ai/schemas/brief_v1.json`). Ganhos de instrução-following dos modelos novos viram confiabilidade direta, sem prompt-hacking.
4. **Prompts versionados e hasheados** (`ai/prompts/release_brief_v1.md`). Permite A/B (modelo×prompt) e rollback.
5. **Observabilidade de qualidade de IA.** Logar por chamada: `model_id`, taxa de aterramento, rejeições de guardrail, latência, custo, schema_version. Assim dá para **ver** que um modelo novo é melhor — não chutar.
6. **Cadeia de fallback graciosa:** frontier → local → determinístico. Sempre há piso.
7. **Custo/latência como flag.** Features de maior custo (ex.: Ask-the-IPCA ao vivo na demo pública) ficam isoladas atrás de flags, permitindo ativação futura sem re-arquitetura.
8. **Sem hard-code de premissas de modelo** (janela de contexto, formato de tool-call, limites de token): tudo atrás da abstração de provider.

> Princípio operacional: **a inteligência é plugável; o aterramento e a segurança são fixos.** Atualizar o cérebro nunca toca a camada de evidência/guardrail.

### 3.6 Reprodutibilidade e auditoria

Todo artefato de IA acompanha `metadata.json`:

```json
{
  "generated_at": "2026-05-28T13:00:00Z",
  "model_id": "claude-opus-4-7",
  "provider": "anthropic",
  "prompt_version": "release_brief_v1",
  "prompt_hash": "sha256:...",
  "evidence_hash": "sha256:...",
  "schema_version": "brief_v1",
  "data_sources": ["IBGE/SIDRA", "BCB/SGS"],
  "reference_month": "2026-04"
}
```

### 3.7 Human-in-the-loop (fluxo release-day)

```
Action detecta IPCA novo ─▶ roda pipeline determinístico ─▶ monta evidence table
   ─▶ gera brief grounded ─▶ ABRE PR com reports/<mês>/ ─▶ você revisa ─▶ merge = aprovação ─▶ publica
```

Merge é a aprovação humana. A IA nunca fala em público sem revisão. (Detalhes de automação na seção 8.)

> **Status (v0.1):** este fluxo automatizado de detecção→PR é **alvo da v0.2** (§12). Em v0.1, o refresh mensal de dados commita direto (`refresh-data.yml`) e o **brief de IA é regenerado manualmente (BYOK)** antes de publicar — a revisão humana acontece, mas ainda não via PR automático.

### 3.8 Features de IA por versão

**v0.1 — IA visível, aterrada, em batch (sem live API na demo):**
- Brief **determinístico** sempre presente (piso).
- Brief de **IA pré-gerado** como artefato versionado + `metadata.json`.
- **Evidência clicável:** cada afirmação do brief é um chip que aponta para o número/gráfico que a sustenta (`evidence_id` → fonte). "Toda frase auditável com um clique" — sinal AI-native novo e 100% seguro com conteúdo pré-gerado.
- **Trace de orquestração persistido** (`reports/<mês>/ai_trace.json` + expander "como a IA montou este brief"): o brief é gerado por **uma execução real com tool-use** (rodada uma vez), e o trace (tool calls → evidence_ids → claims) é salvo. É o que torna "a IA orquestra" verdadeiro, não slogan — sem viewer dedicado, só o replay do que já foi gerado.
- O **output** de IA aparece **por padrão** na página executiva. A demo pública roda em **"AI Replay Mode"** (brief e trace pré-gerados e auditados); live calls ficam atrás de BYOK local. Rotular como "AI Replay Mode", nunca "AI disabled".

**v0.2 — IA agêntica (o showcase real):**
- **Ask the IPCA**: Q&A com tool-use aterrado sobre a Tool API (3.2). Cada resposta numérica traça a `evidence_id`; recusa fora de escopo; não navega na internet; não aconselha investimento.
- Demo pública: ~6–8 perguntas **pré-respondidas** e auditáveis (sem chave). **BYOK** destrava Q&A ao vivo localmente.
- Construído sobre a **mesma** Tool API do v0.1 — o upgrade é natural, não um rewrite.

---

## 4. Metodologia

### 4.1 Fontes
BCB/SGS (`config/series_sgs.yaml`) e IBGE/SIDRA tabela 7060 (`config/sidra_7060.yaml`). Documentar o que é **oficial**, **calculado** e **aproximado**.

### 4.2 Contribuições
- Mensal: `contribution_mom = weight * mom / 100` (p.p.).
- 12m: manter `contribution_12m_simple` e `contribution_12m_chain`, documentando a diferença. Corrigir a primeira janela encadeada (5.x, polish).

### 4.3 Difusão
- **Fonte primária do painel:** série oficial BCB (SGS 21379).
- Difusão calculada por subitens **apenas** para granularidade por grupo, auditoria e exploração — via função centralizada que **exclui `NaN`** (5.1).

### 4.4 Dessazonalização e momentum *(decisão nova)*
- **Problema:** as variações mensais da SIDRA/SGS são brutas (NSA). Anualizar 3m de série NSA eleva o padrão sazonal à 4ª potência e pode enganar; e "SAAR" significa *Seasonally Adjusted* — usar a sigla sobre NSA é incorreto.
- **Decisão v0.1:** **não anualizar série NSA.** Mostrar **acumulado 3m** e/ou **MM3M**, rotulados claramente. Remover o rótulo "saar" onde não houver ajuste sazonal. Caveat **visível na UI** (não escondido em `methodology.md`).
- **Decisão v0.2:** ajuste sazonal via **STL** (`statsmodels.tsa.seasonal.STL`, Python-puro) para headline + núcleos; só então oferecer "3m anualizado (SA)". X-13ARIMA-SEATS fica como opção avançada futura. Não vender como "BCB-like" sem caveat.

### 4.5 Núcleos
- Presets em `config/core_sets.yaml`. Default `bcb_compact` = EX0, EX3, MS, DP, P55.
- Média válida **só com o conjunto completo** (5.4); sinalizar incompletude. Campo `require_complete` por preset.

### 4.6 Percentis e z-score
- Percentil expansivo, mínimo 24 obs, com **midrank para empates** (5.x), em **uma única função** usada por `transforms.py` e `audit.py`.
- Renomear `percentile_since_2012` → `expanding_percentile` + metadados de janela efetiva (polish; em v0.1 ao menos relabel na UI).

---

## 5. Correções (reclassificadas)

Critério de bloqueio: *produz output visivelmente errado que um economista atento pega num screenshot, ou compromete integridade de dados.*

### 5.1 — Bloqueantes de v0.1 (corrigir antes do lançamento)

| # | Correção | Onde (verificado no código) | Aceite |
|---|----------|------------------------------|--------|
| B1 | **Difusão exclui `NaN`** via função centralizada `calculate_diffusion_from_items()` | `dashboard/app.py:172`, `src/ipca_dashboard/audit.py:264` | `[1.0, -0.5, NaN]` → 50.0; app e audit usam a mesma função |
| B2 | **Média de núcleos**: reindex de colunas, `skipna=False`, flags `n_members_expected/available/is_complete/missing_members`; sem `KeyError` | `src/ipca_dashboard/transforms.py:115-116` | preset com membro ausente não quebra; média incompleta = `NaN`; UI avisa |
| B3 | **Ranking sem duplicação** | `src/ipca_dashboard/charts.py:77-79` | 9 grupos com `top_n=10` → 9 barras, não 18 |
| B4 | **Percentil com midrank, centralizado** | `transforms.py:34` **e** `audit.py:343` | série constante → ~p50, não p100; uma função só |
| B5 | **Pipeline não sobrescreve dados bons**: staging + `--strict` + promoção atômica `os.replace` por arquivo | `src/ipca_dashboard/pipeline.py:60-68` | validação bloqueante mantém `data/processed/` intacto; CI testa o cenário |
| B6 | **Freshness de séries críticas** | `src/ipca_dashboard/alerts.py:51`, `validation.py` | série crítica defasada → aviso na UI; build strict bloqueia se faltar no mês mais recente |

Função-alvo do percentil (com guard):

```python
def percentile_midrank(window: pd.Series, current: float) -> float:
    valid = window.dropna()
    if len(valid) == 0 or pd.isna(current):
        return float("nan")
    less = int((valid < current).sum())
    equal = int((valid == current).sum())
    return 100 * (less + 0.5 * equal) / len(valid)
```

### 5.2 — Polish / pós-v0.1

- **P1 Chunking SGS** (`fetch_bcb.py`). *Decisão:* **testar empiricamente** se `--start-sgs 2012-01` falha hoje (séries mensais raramente estouram a janela). Se falhar → implementar chunking (a auditoria longa é feature de credibilidade, **não** neutralizar). Se não falhar → não-bloqueante. Não deixar comando público quebrável no Quickstart.
- **P2 Primeira janela 12m encadeada** (`transforms.py:195`) — recupera 1 mês no início.
- **P3 Renomear percentil** para refletir janela efetiva.
- **P4 Cooldown de alertas** → **v0.3** (depende de `alerts_history.parquet`, que não existe; sem estado persistente, cooldown é conceitualmente incompleto). Em v0.1: alertas determinísticos + severidade + mensagem, sem promessa de cooldown.

---

## 6. Pipeline e robustez

- **Staging atômico:** transformar em memória → validar → se `block` em modo strict, abortar antes de promover → escrever `data/processed_staging/` → promover com `os.replace` por arquivo. Default público: CI roda `--strict`.
- **Centralização:** difusão e percentil em funções únicas reaproveitadas por app/audit/pipeline.
- **Validações novas:** `critical_series_freshness`, `core_set_completeness`, `sidra_required_variables_present`, `bcb_required_series_present`, `diffusion_missing_excluded`, `processed_data_not_stale`. Severidade padronizada `pass|warn|block`.
- **Cache do Streamlit por assinatura de arquivo** (mtime) para recarregar após novo build sem limpar cache manual.

---

## 7. Dashboard e design

**Decisão:** manter Streamlit em v0.1; **não** tentar fazê-lo parecer SaaS premium. Objetivo estético do app: *limpo, confiável, research-grade, sem firula*. O **design premium vai no artefato estático compartilhável**, não no Streamlit.

- Aplicar `config/chart_theme.yaml` de fato (`load_chart_theme()`, template Plotly único, paleta por categoria macro).
- Página executiva: cards (m/m, 12m, 3m acumulado/MM3M, média núcleos, difusão MM3M, **badge de regime**), brief (determinístico + IA pré-gerado com evidência clicável), decomposição do mês, difusão com bandas, alertas ativos, downloads + links.
- Avisos: completude de preset de núcleos; freshness; caveat de dessazonalização; estado da IA.
- `dashboard/components.py` + `dashboard/theme.py` para tirar a cara de "notebook virou Streamlit".

---

## 8. Distribuição e automação

A distribuição é feature de primeira classe — é o motor de crescimento no LinkedIn.

### 8.1 Artefato estático compartilhável

```
src/ipca_dashboard/reporting/
  build_report.py
  render_markdown.py
  render_static_charts.py   # PNG via Plotly+kaleido (atenção: kaleido pode ser chato no CI)
```

Saídas por mês: `evidence.json`, `brief.md` (+ `ai_brief.md` quando houver), `charts/*.png`, `metadata.json`, e um `report.md`/`report.png` "hero".

### 8.2 Onde os artefatos vivem *(decisão de engenharia)*
**Não commitar PNGs mensais no `main`** (git guarda todas as versões → repo incha com o tempo). Publicar via Action em **GitHub Releases** ou **branch `gh-pages`/Pages**. `main` fica limpo; `reports/latest.*` pode ser um ponteiro sobrescrito para diffs limpos.

### 8.3 Detecção de divulgação (não "cron mensal burro") *(alvo v0.2)*
O IPCA tem data específica. Action **diária** numa janela provável que **checa dado novo e só dispara ao detectar** (`daily_check_for_new_ipca_release.yml`). Ao detectar: roda pipeline → gera relatório → **abre PR** (HITL, seção 3.7). **Em v0.1**, o refresh é mensal e commita direto (`refresh-data.yml`); a detecção diária + PR automático ficam para a v0.2.

### 8.4 Bilinguismo (sem drift)
- **README em inglês** como principal (alcance no GitHub) + **`README.pt-BR.md` curto** apontando para ele. Não espelhar 100% (espelho gera drift).
- **Artefato compartilhável/relatório em PT-BR por default** (audiência LinkedIn Brasil). UI com toggle PT-BR/EN depois.

### 8.5 Demo pública
Streamlit Community Cloud em v0.1, **com dados processados** publicados (Releases/Pages) e **IA pré-gerada** (sem chave em runtime). Sem dados fictícios: se API cair, erro claro + último dado válido com timestamp.

---

## 9. Open-source mínimo

**Obrigatório v0.1:** `LICENSE` (MIT), README excelente (EN) + `README.pt-BR.md`, `SECURITY.md`, `.env.example`, `.streamlit/secrets.toml.example`, `.gitignore` que bloqueia secrets e dados, GitHub Actions (testes + evals + check-no-secrets), 1 screenshot/GIF hero.

**Bom, não obrigatório:** `CONTRIBUTING.md` curto, `CODE_OF_CONDUCT.md` simples (Contributor Covenant — barato e positivo).

**Adiar (até haver tração/contribuidores):** `CITATION.cff`, múltiplos issue templates (um basta), PR template sofisticado, `ROADMAP.md` extenso.

**Secrets:** regra absoluta — nenhuma chave versionada. `.env`/`secrets.toml` reais no `.gitignore`; só `.example` no repo. Script `scripts/check_no_secrets.py` no CI. IA off por default em execução interativa; output pré-gerado visível.

---

## 10. Testes e evals

**Determinísticos (CI, sem rede):**
```
test_diffusion_excludes_missing_mom
test_core_mean_requires_complete_member_set
test_contribution_ranking_does_not_duplicate_categories
test_percentile_midrank_handles_ties           # transforms E audit
test_pipeline_does_not_overwrite_processed_on_blocking_validation
test_critical_series_are_fresh
test_chain_contribution_available_after_12_months   # polish
test_no_api_key_required_by_default
```

**`make test-ai-contract` (CI, sempre, sem rede):**
```
NoAIProvider sempre passa
guardrail rejeita claim sem evidence_ids
guardrail recusa fora de escopo
guardrail bloqueia número fora da evidência
guardrail de política monetária
casos de regime conferem com esperados (classificador determinístico)
```
**`make eval-model MODEL=<id>` (manual / workflow_dispatch, requer chave — NÃO exigido de contribuidores):** roda o eval gate da seção 3.5 contra um modelo real.

Lint/format: `ruff` (`select = ["E","F","I","UP","B","SIM"]`, line-length 100). Lockfile (`uv.lock` ou `requirements.lock`) para reprodutibilidade.

---

## 11. Segurança

`SECURITY.md` com: nunca abrir issue pública com chave vazada; como reportar vulnerabilidade; como remover segredo commitado por acidente; política de `.env`/`secrets.toml`. Providers de IA nunca logam/serializam chave. Cadeia de fallback garante operação sem chave.

---

## 12. Roadmap

- **v0.1.0-public** — 6 bugs bloqueantes; difusão/percentil centralizados; freshness; staging strict; relabel de momentum + caveat NSA; OSS mínimo; página executiva limpa; **brief determinístico + um brief de IA aterrado com trace persistido**; regime classifier mínimo; artefato estático + hero via `make release-report` **manual**; demo em AI Replay Mode. (Ver §16 para o corte Must/Should/Nice.)
- **v0.2.0-ai-agentic** — **Ask the IPCA** agêntico aterrado (BYOK live + replay na demo); STL (SA) + 3m anualizado SA; **detecção de release diária + PR automático**; `OllamaProvider`/segundo provider; eval harness completo; observabilidade de IA; capability tiers ativos; evidência clicável; tema/components polidos.
- **v0.3.0-research-workflow** — `alerts_history.parquet` + cooldown + status (new/repeated/resolved/suppressed); comparação manual com Focus/consenso; calendário de divulgação; export HTML/PDF; heatmap de difusão por grupo.
- **v1.0.0** — API pública estável do pacote; migração opcional p/ namespace `openipca` com alias; cobertura mínima definida; possível frontend premium se houver tração.

---

## 13. Critérios de aceite (Definition of Done)

**v0.1:**
```
[ ] Roda localmente seguindo só o README.
[ ] Pipeline executa com dados oficiais; dashboard abre sem erro.
[ ] 6 bugs bloqueantes corrigidos, com testes verdes no CI.
[ ] Difusão e percentil centralizados (app + audit).
[ ] Momentum NSA não é anualizado; caveat de sazonalidade visível na UI.
[ ] Pipeline strict não sobrescreve dados bons.
[ ] Brief determinístico + brief de IA pré-gerado, com evidência clicável, visíveis por default.
[ ] Todo número da IA rastreia a evidence_id (guardrail testado).
[ ] Artefato de IA carimbado com metadata (model/prompt/hashes).
[ ] LICENSE, README (EN+PT-BR curto), SECURITY, .env.example, .gitignore.
[ ] Sem secrets versionados (check no CI).
[ ] Screenshot/GIF hero + disclaimer de não-afiliação.
[ ] Demo pública sem live AI.
```

**v0.2:**
```
[ ] Tool API determinística estável e documentada.
[ ] Ask the IPCA agêntico aterrado; recusa fora de escopo; não inventa número.
[ ] STL (SA) disponível; "3m anualizado (SA)" rotulado corretamente.
[ ] make eval-model bloqueia promoção de modelo que não passa o gate.
[ ] CI não chama API externa.
```

---

## 14. Riscos e mitigação

| Risco | Mitigação |
|-------|-----------|
| Parecer "mais um app com GPT" | IA **aterrada** (evidence_id) é o oposto do wrapper genérico; tese macro forte; metodologia transparente |
| Erro metodológico público (ex.: SAAR sobre NSA) | Não anualizar NSA em v0.1; caveat visível; STL em v0.2; testes/auditoria |
| IA falar besteira em público | Human-in-the-loop (PR); guardrails; fallback determinístico |
| Vazar chave | `.gitignore` + `.example` + check no CI + IA off por default |
| Custo de IA | Demo sem live AI; pré-geração; BYOK; flags de custo destraváveis quando modelos baratearem |
| Modelo novo regredir qualidade | Eval gate (3.5): só promove quem mantém aterramento e não regride |
| Repo inchar com artefatos | Publicar em Releases/Pages, não no `main` |
| Nunca lançar (over-scope) | Escopo v0.1 enxuto; governança pesada adiada |

---

## 15. Frase-guia

> **OpenIPCA é um monitor open-source do IPCA com núcleo macro determinístico, IA que orquestra ferramentas auditáveis, claims rastreados a evidências, replay público do raciocínio da IA e revisão humana antes de publicar. Não depende de IA para funcionar; usa IA para transformar dados oficiais em leitura macro explicável e compartilhável — e é model-upgradable: absorve modelos melhores via evals e rollback, sem reescrever o sistema.**

A diferença de uma palavra que organiza o projeto inteiro: a IA **orquestra**, não **narra**.

---

## 16. v0.1 scope lock (Must / Should / Nice)

Corte de escopo para não re-inflar o projeto. **Só "Must" bloqueia o lançamento.** Esta seção tem precedência sobre qualquer ambição descrita acima.

**MUST (lançar):**
- B1–B6 (seção 5.1) com testes.
- Não anualizar NSA + caveat visível (4.4).
- OSS: MIT, README (EN) + `README.pt-BR.md` curto, SECURITY, `.env.example`, `.gitignore`, CI (`test` + `check-no-secrets`), disclaimer de não-afiliação.
- Camada de IA (CP6, todos Must): **Tool API determinística** + **evidence table** (§3.2) + **o conjunto mínimo de guardrails da §3.3** — aterramento por `evidence_ids[]`, recusa fora de escopo, bloqueio de número fora da evidência, e guardrail de política monetária. Nenhum desses é "ambição não-bloqueante".
- Brief determinístico (piso) + **1** brief de IA (CP7) com tool-use sobre a Tool API acima, **trace persistido**, validado pelos guardrails; em qualquer falha (sem chave/erro/guardrail) degrada para o determinístico.
- Regime classifier determinístico mínimo (~4–5 regimes; alimenta badge + aterra a IA).
- 1 screenshot/GIF hero + `report.md` + PNG via `python -m ipca_dashboard.reporting.build_report --latest` **manual** (comando canônico portável; sem Makefile como interface oficial).

**SHOULD (logo após, se for rápido):**
- Evidência clicável (chips); estrutura `reports/latest/`; `test-ai-contract` separado de `eval-model`; tema/components.

**NICE / DEFER (v0.2+):**
- Ask the IPCA live (BYOK) + replay Q&A; detecção diária + PR automático; STL (SA); `OllamaProvider`/2º provider; Trust Panel; badges por elemento; taxonomia de 7 regimes; cooldown/histórico de alertas.

**Regras anti-overengineering (do projeto):**
1. Ideia nova entra como **Nice** por default; só vira Must com justificativa explícita.
2. Rodada de revisão de spec **não adiciona Must** — só corta ou esclarece.
3. App leve: Streamlit + pandas, **sem infra nova**; IA = artefato gerado por script, **sem serving**.
