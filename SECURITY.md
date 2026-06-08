# Security Policy

OpenIPCA is a research and education tool. It uses public official data and runs locally.
Still, the optional AI layer involves API keys, so please follow these rules.

## Never commit secrets

- **Do not commit API keys** (Anthropic, OpenAI, or any provider).
- Real secret files are git-ignored: `.env`, `.env.*`, `.streamlit/secrets.toml`.
- Only the example files are tracked: `.env.example`, `.streamlit/secrets.toml.example`.
- CI runs `scripts/check_no_secrets.py` to catch accidental key commits.
- The monthly data refresh regenerates the AI brief/replay using an OpenAI key kept in
  **GitHub Actions secrets** (encrypted, never in the repo, and not exposed to fork PRs —
  the `refresh-data` workflow runs only on schedule / manual dispatch).

## If you accidentally commit a key

1. **Revoke/rotate the key immediately** at the provider — assume it is compromised.
2. Remove it from history (e.g. `git filter-repo`) and force-push, or contact the
   maintainer privately first.
3. Do **not** open a public issue that contains the leaked key.

## Reporting a vulnerability

Please report security issues **privately** via the GitHub "Report a vulnerability"
feature (Security tab) or by contacting the maintainer
[@Brunosavastano](https://github.com/Brunosavastano), rather than opening a public issue.
We will respond as soon as reasonably possible.

## Scope reminder

OpenIPCA does not provide investment advice and is not affiliated with the IBGE or the
Banco Central do Brasil. See the disclaimer in the [README](README.md).
