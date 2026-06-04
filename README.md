# OpenIPCA

**Brazilian inflation beyond the headline.**

[![tests](https://github.com/Brunosavastano/OpenIPCA/actions/workflows/tests.yml/badge.svg)](https://github.com/Brunosavastano/OpenIPCA/actions/workflows/tests.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)

OpenIPCA is an open-source macro research dashboard for Brazilian inflation. It turns
official data from **IBGE/SIDRA** and **BCB/SGS** into IPCA decomposition, core inflation,
diffusion and auditable alerts. The numbers are deterministic; the AI is **grounded** — it
*orchestrates* those numbers and every claim traces to an evidence item, never an invented
figure. Its most visible piece is **Ask the IPCA**: a grounded Q&A box that reasons about the
release in plain Portuguese, where every number traces to an evidence id. It answers live and
falls back to audited, pre-generated answers, so a grounded reply is always there.

> 🇧🇷 Leia em português: [README.pt-BR.md](README.pt-BR.md)

---

## ⚠️ Disclaimer

OpenIPCA is a research and education tool. It uses public data sources and deterministic
calculations to support inflation analysis. It is **not investment advice**, does **not**
provide monetary-policy forecasts, and **may contain errors**. It is **not affiliated with,
endorsed by, or connected to the IBGE or the Banco Central do Brasil** — it only consumes
their public data. Always verify critical analysis against the official sources.

---

## Why this exists

The headline IPCA number doesn't tell the whole story. A single month can hide whether
inflation is *broad or concentrated*, whether *cores* are benign or pressured, and whether
*momentum* is accelerating. OpenIPCA reconstructs the release the way a macro research desk
would read it — decomposition, cores, diffusion and momentum — from official data, with the
methodology fully in the open.

## Features

- **Ask the IPCA** — a grounded, live Q&A box. Ask in Portuguese and get an answer anchored
  in the official data, where *every number traces to an evidence id*. It answers live and
  falls back to audited, pre-generated answers, so a grounded reply is always there. It reasons
  about the release, confronts external hypotheses ("did an oil shock cause
  this?") against the numbers, refuses prompt-injection, and never gives investment advice or
  Copom/Selic forecasts.
- **Decomposition** of IPCA by group, subgroup, item and subitem (contributions in p.p.).
- **Core inflation** monitor with configurable presets (`config/core_sets.yaml`).
- **Diffusion** (official BCB series + a calculated breakdown by group).
- **Auditable alerts** from declarative rules (`config/alert_rules.yaml`).
- **Deterministic macro brief** + inflation-regime classification.
- **Optional AI layer** (off by default, BYOK): a grounded, auditable brief — every claim
  cites an evidence id; no AI-generated numbers.
- **Validation & audit** reports so you can tell what's official, calculated or approximate.

## Quickstart

```bash
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# macOS / Linux:         source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

# Fetch official data and build the processed datasets:
python -m ipca_dashboard.pipeline run --start 2020-01

# Launch the dashboard:
streamlit run dashboard/app.py
```

Run the test suite with `python -m pytest`.

## Data sources

- **BCB/SGS** — IPCA headline, macro aggregates, cores and official diffusion.
- **IBGE/SIDRA table 7060** — weights, variations and the group → subitem hierarchy.

No fictitious data is ever used as a fallback: if an API is unavailable, the app fails
explicitly. See [methodology.md](methodology.md) for formulas and limitations.

## AI layer (optional)

The app works **fully without AI**. The AI layer is **disabled by default** and uses
**BYOK** (bring your own key) — no keys are stored in the repo. When enabled, the model
*orchestrates* deterministic tools and an evidence table; it never invents numbers, and
every claim is validated against an existing evidence id. See [SECURITY.md](SECURITY.md)
for key handling.

It is **model-agnostic** (OpenAI, Anthropic or Google Gemini behind one provider seam — the
model is config, not code) and the safety floor is code: guardrails reject prompt-injection
and off-scope questions *before* the model, and reject ungrounded numbers, monetary-policy
forecasts and asset advice *after* it. **Ask the IPCA** answers live on a free model and falls
back to audited, pre-generated answers when that's unavailable, so a grounded answer is always
visible — the AI never blocks the product. Run it locally with your own key for unrestricted live Q&A.

## Contributing

Issues and PRs are welcome. Please don't commit API keys — CI enforces this via
`scripts/check_no_secrets.py`. See [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE) © 2026 Bruno Savastano
