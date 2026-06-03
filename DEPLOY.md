# Deploy da demo pública — e como garantir que a IA apareça

Guia objetivo para publicar o OpenIPCA (Streamlit Community Cloud) com o
**"Pergunte ao IPCA"** realmente respondendo. O app **funciona sem IA** (todos os
números são determinísticos); esta página trata só de tornar a IA **visível** na
demo pública.

## Como a demo decide a resposta

| Selo na tela | Quando |
|---|---|
| 🟢 **ao vivo** | há chave de IA no deploy e a cota está disponível → o modelo responde na hora |
| 🗂️ **pré-gerada** | a IA ao vivo está indisponível (sem chave / cota estourada / erro) **e** a pergunta tem um par no replay |
| ⚪ **indisponível** | sem chave **e** sem replay para aquela pergunta → fallback honesto (aponta para o painel/brief) |
| 🚫 **recusada** | injeção ou pergunta fora do escopo (apenas inflação/IPCA) |

**Conclusão prática:** para o visitante do LinkedIn ver IA de verdade, você precisa
de **pelo menos um** entre (1) chave no deploy e (2) replay gerado. O ideal é **os
dois**: chave para o "ao vivo" + replay como rede de segurança quando a cota grátis
estourar.

---

## Passo 1 — Gerar o replay (recomendado: use o seu modelo mais forte)

O replay é o que aparece **sem chave/cota**. Como ele é gerado **uma vez**, na sua
máquina, e fica auditável no repositório, **não precisa usar o Gemini**: use o
provider mais forte que você tiver (gpt-5.x / Claude) para respostas de máxima
qualidade. A demo *ao vivo* continua no Gemini grátis (para estranhos); o *replay*
pode ser premium. O app é model-agnostic — isto já é suportado.

1. No seu `.env` local (nunca commitado), aponte para o provider forte, por ex.:
   ```
   OPENIPCA_AI_ENABLED=true
   OPENIPCA_AI_PROVIDER=openai
   OPENIPCA_AI_MODEL=gpt-5.4
   OPENAI_API_KEY=sua-chave
   ```
2. Garanta que as dependências opcionais de IA estejam instaladas no ambiente local:
   ```
   python -m pip install -e ".[ai]"
   ```
3. Gere:
   ```
   python -m ipca_dashboard.ai.qa_replay
   ```
4. Leia o resumo no fim:
   - `Wrote N/M grounded replay pair(s)` — quantas perguntas aterraram.
   - Se **N < M**: algumas não aterraram (modelo fraco ou pergunta difícil). Troque
     de modelo ou revise as perguntas em `CURATED_QUESTIONS` e rode de novo.
   - Se **N == 0**: a demo **não** terá rede de segurança — corrija antes de seguir.
5. Confira `reports/qa/replay.json` (respostas aterradas, **sem nenhuma chave dentro**)
   e faça commit dele.

> As perguntas são as `CURATED_QUESTIONS` em `src/ipca_dashboard/ai/qa_replay.py`
> (também os botões da página). Edite-as à vontade antes de gerar.

---

## Passo 2 — Chave Gemini no deploy (o "ao vivo" para estranhos)

No **Streamlit Community Cloud**: app → **Settings → Secrets** → cole (formato TOML,
**com aspas**):

```toml
OPENIPCA_AI_ENABLED = "true"
OPENIPCA_AI_PROVIDER = "gemini"
OPENIPCA_AI_MODEL = "gemini-2.0-flash"
GOOGLE_API_KEY = "sua-chave-google"
```

- A chave fica **no servidor**, nunca no navegador nem no repositório.
- O app espelha esses secrets para variáveis de ambiente no boot
  (`bridge_secrets_to_env`), então a configuração acima **ativa** a IA — sem isso o
  app não enxergaria a chave (ele lê `os.environ`, e o Streamlit não exporta secrets
  como env vars automaticamente).
- **Sem rate-limit, de propósito:** se a cota grátis do Gemini estourar, a demo cai
  no replay (ou no fallback honesto) — não quebra. Trivial de adicionar depois.

---

## Passo 3 — Publicar

Streamlit Community Cloud → **New app** → repositório → branch `main` → arquivo
`dashboard/app.py`. Pronto.

---

## Matriz: o que o visitante vê

| Chave no deploy | Replay commitado | Resultado |
|:---:|:---:|---|
| ✅ | ✅ | **Ideal.** Ao vivo; cai no replay se a cota estourar. |
| ❌ | ✅ | Sempre pré-gerada (auditada). IA visível, sem custo de chave. |
| ✅ | ❌ | Ao vivo; **⚪ indisponível** quando a cota estourar. |
| ❌ | ❌ | **⚪ indisponível** — IA invisível na demo. **Evite.** |

---

## Segurança (já garantido pelo código)

- Chave só em `.env` (local) ou Secrets (deploy) — **nunca no repositório**;
  `scripts/check_no_secrets.py` roda no CI.
- Injeção e fora-de-escopo são barrados **antes** do modelo; previsão de
  Copom/Selic e recomendação de ativo são barradas **na saída**.
- A resposta do modelo é renderizada como **texto inerte** (sem HTML), então uma
  resposta forjada não injeta nada na página.
- Todo número exibido é rastreável a uma evidência citada (expander "Evidências").
