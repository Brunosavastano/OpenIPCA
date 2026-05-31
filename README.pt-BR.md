# OpenIPCA

**A inflação brasileira além do headline.**

> 🇬🇧 The primary documentation is in English: [README.md](README.md). Este é um resumo em português.

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

## Início rápido

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# Baixar dados oficiais e construir os datasets processados:
python -m ipca_dashboard.pipeline run --start 2020-01

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
