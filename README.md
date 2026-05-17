# IPCA Macro Dashboard

Aplicação analítica para acompanhar IPCA, decomposição, núcleos, difusão e alertas automáticos com linguagem de research macro. O projeto usa fontes públicas oficiais: BCB/SGS e IBGE/SIDRA.

## Objetivo

Entregar um monitor reprodutivel para responder, no dia da divulgacao do IPCA:

- de onde veio o headline;
- se a inflação está localizada ou disseminada;
- se os núcleos estão benignos ou pressionados;
- quais alertas macro devem ser observados.

## Estrutura

```text
config/                 parâmetros de séries, SIDRA, núcleos e alertas
src/ipca_dashboard/     pacote Python do pipeline analitico
dashboard/app.py        dashboard Streamlit
data/raw/               dados brutos baixados das APIs
data/processed/         dados tratados em Parquet
outputs/                diagnóstico e relatório de validação
tests/                  testes automatizados
```

## Instalacao

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Execução

Baixar dados e processar:

```bash
python -m ipca_dashboard.pipeline run --start 2020-01
```

Rodar apenas a coleta:

```bash
python -m ipca_dashboard.pipeline fetch --start 2020-01
```

Rodar apenas o processamento de dados brutos ja baixados:

```bash
python -m ipca_dashboard.pipeline build
```

Abrir o dashboard:

```bash
streamlit run dashboard/app.py
```

Rodar a auditoria de acurácia econométrica sem alterar os Parquets do dashboard:

```bash
python -m ipca_dashboard.audit --start-sgs 2012-01 --start-sidra 2020-01
```

## Outputs

- `data/processed/bcb_series_monthly.parquet`: séries SGS tratadas.
- `data/processed/ipca_items_monthly.parquet`: hierarquia SIDRA com contribuicoes.
- `data/processed/core_metrics_monthly.parquet`: métricas dos núcleos por preset.
- `data/processed/alerts.parquet`: alertas ativos.
- `outputs/validation_report.csv`: checagens de integridade.
- `outputs/diagnostic_latest.json`: narrativa automática do último mês.

## Auditoria econométrica

A auditoria salva relatórios em `outputs/audit/`:

- `coverage_report.csv`: cobertura temporal, duplicidades e meses faltantes.
- `reconciliation_report.csv`: reconciliação SGS/SIDRA, contribuições e difusão.
- `metric_window_report.csv`: janela efetiva de 12m, 3m saar, percentis e z-score.
- `alert_sensitivity_report.csv`: sensibilidade dos alertas a janelas históricas.
- `econometric_accuracy_report.md`: síntese metodológica da auditoria.

## Testes

```bash
python -m pytest
```

## Limitacoes

- O MVP usa Brasil nacional e frequência mensal.
- A tabela SIDRA 7060 reflete a estrutura atual do IPCA a partir de 2020; historicos anteriores exigem tabelas legadas.
- Alertas push por Slack, Telegram ou e-mail ainda não foram implementados; os alertas ficam no dashboard e em Parquet.
- O dashboard falha explicitamente se as APIs públicas estiverem indisponíveis; nenhum dado fictício é usado como fallback.

## Próximos passos

- Integrar agenda de divulgacao.
- Adicionar comparação com Focus/consenso.
- Implementar exportação PDF pós-divulgação.
- Adicionar dessazonalização opcional para métricas de momentum.
