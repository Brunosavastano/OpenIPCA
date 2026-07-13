# OpenIPCA

**A inflação brasileira além do headline.**

> 🇬🇧 The primary documentation is in English: [README.md](README.md). Este é um resumo em português.

**[➡️ Abra o app — openipca.streamlit.app](https://openipca.streamlit.app)**

[![Painel executivo do OpenIPCA: KPIs, regime inflacionário, leitura do mês e Análise OpenIPCA auditável](docs/hero.png)](https://openipca.streamlit.app)

OpenIPCA é um dashboard open-source de pesquisa macro para a inflação brasileira. Ele
transforma dados oficiais do **IBGE/SIDRA** e do **BCB/SGS** em decomposição do IPCA,
núcleos, difusão e alertas auditáveis. Os números são determinísticos; a interpretação pode
ser orquestrada por IA, e toda afirmação da IA é rastreável a uma evidência.

## ⚠️ Aviso

O OpenIPCA é uma ferramenta de pesquisa e educação. Usa dados públicos e cálculos
determinísticos para apoiar a análise de inflação. **Não é recomendação de investimento**,
**não** fornece previsão de política monetária e **pode conter erros**. **Não é afiliado,
endossado ou conectado ao IBGE nem ao Banco Central do Brasil** — apenas consome seus dados
públicos. Verifique análises críticas nas fontes oficiais.

## Por que existe

O número cheio do IPCA não conta a história inteira. Um único mês pode esconder se a
inflação está *disseminada ou concentrada*, se os *núcleos* estão benignos ou pressionados
e se o *momentum* está acelerando. O OpenIPCA reconstrói a divulgação como uma mesa de
research leria — decomposição, núcleos, difusão e momentum — a partir de dados oficiais,
com a metodologia toda aberta.

O detector consulta a competência oficial a cada cinco minutos na janela de divulgação. Quando
SIDRA e as séries críticas do BCB estão completos, o mês novo é validado e publicado sem esperar
pela IA. Brief e replay são propostos em PR separado e ficam ocultos enquanto estiverem defasados.
O Pergunte ao IPCA continua respondendo sem chave: para perguntas cobertas pelas tools,
monta uma resposta direta e rastreável com as evidências da competência atual.

## Início rápido

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# Baixar dados oficiais e construir os datasets processados
# (defaults: BCB/SGS desde 2012-01 — os percentis precisam da história longa —
#  e IBGE/SIDRA desde 2020-01, primeiro mês da tabela):
python -m ipca_dashboard.pipeline run

# Detectar uma competência oficial nova e fazer o refresh incremental estrito:
python scripts/probe_ipca_release.py --json
python -m ipca_dashboard.pipeline refresh-latest --expected-month YYYY-MM --strict

# Abrir o dashboard:
streamlit run dashboard/app.py
```

## Camada de IA (opcional)

O app funciona **100% sem IA**. A camada de IA fica **desligada por padrão** e usa **BYOK**
(traga sua própria chave) — nenhuma chave fica no repositório. Quando ligada, o modelo
*orquestra* ferramentas determinísticas e uma tabela de evidências; nunca inventa números, e
toda afirmação é validada contra uma evidência existente.

## Licença

[MIT](LICENSE) © 2026 Bruno Savastano · Detalhes e metodologia: [README.md](README.md) · [methodology.md](methodology.md)
