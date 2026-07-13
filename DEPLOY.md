# Deploy da versão pública — e como garantir que a IA apareça

Guia objetivo para publicar o OpenIPCA (Streamlit Community Cloud) com o
**"Pergunte ao IPCA"** realmente respondendo. O app **funciona sem IA** (todos os
números são determinísticos); esta página trata só de tornar a IA **visível** na
versão pública.

## Como a versão pública decide a resposta

| Selo na tela | Quando |
|---|---|
| 🟢 **ao vivo** | há chave de IA no deploy e a cota está disponível → o modelo responde na hora |
| 🗂️ **pré-gerada** | a IA ao vivo está indisponível (sem chave / cota estourada / erro) **e** a pergunta tem um par no replay |
| 🟢 **dados** | sem resposta ao vivo/replay, mas a pergunta é coberta pelas tools → resposta direta com os dados atuais |
| ⚪ **sem evidência** | a pergunta está no escopo, mas as evidências disponíveis não sustentam uma resposta segura |
| 🚫 **recusada** | injeção ou pergunta fora do escopo (apenas inflação/IPCA) |

**Conclusão prática:** a feature responde sobre os dados correntes mesmo sem chave ou
replay. Para o visitante ver interpretação de IA, use os dois: chave para o "ao vivo"
+ replay como rede auditada quando a cota grátis estourar.

---

## Passo 1 — Gerar o replay (recomendado: use o seu modelo mais forte)

O replay é o que aparece **sem chave/cota**. Como ele é gerado **uma vez**, na sua
máquina, e fica auditável no repositório, **não precisa usar o Gemini**: use o
provider mais forte que você tiver (gpt-5.x / Claude) para respostas de máxima
qualidade. O modo *ao vivo* continua no Gemini grátis (para estranhos); o *replay*
pode ser premium. O app é model-agnostic — isto já é suportado.

> **Atualização mensal:** `refresh-data.yml` publica primeiro os dados determinísticos completos,
> sem depender de chave ou modelo. Depois, `refresh-ai-artifacts.yml` gera brief e replay com o
> `OPENAI_API_KEY` dos *secrets* e abre um PR para revisão humana. Enquanto o PR não é aprovado,
> brief e replay antigos ficam ocultos por competência; o painel e o Q&A determinístico continuam
> atuais. O passo manual abaixo serve para a primeira geração ou regeneração fora do ciclo.

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
   - Se **N == 0**: o app **não** terá rede de segurança — corrija antes de seguir.
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
OPENIPCA_AI_MODEL = "gemini-3.5-flash"
GOOGLE_API_KEY = "sua-chave-google"
```

`gemini-2.0-flash` foi desligado pelo Google em junho de 2026. Deploys antigos que
ainda usam esse nome devem atualizar o secret para `gemini-3.5-flash`; o provider
também tenta modelos mantidos quando recebe um erro específico de modelo aposentado.

- A chave fica **no servidor**, nunca no navegador nem no repositório.
- O app espelha esses secrets para variáveis de ambiente no boot
  (`bridge_secrets_to_env`), então a configuração acima **ativa** a IA — sem isso o
  app não enxergaria a chave (ele lê `os.environ`, e o Streamlit não exporta secrets
  como env vars automaticamente).
- **Sem rate-limit, de propósito:** se a cota grátis do Gemini estourar, o app cai
  no replay ou na resposta determinística atual — não quebra. Trivial de adicionar depois.

---

## Passo 3 — Publicar

Streamlit Community Cloud → **New app** → repositório → branch `main` → arquivo
`dashboard/app.py`. Pronto.

---

## Matriz: o que o visitante vê

| Chave no deploy | Replay commitado | Resultado |
|:---:|:---:|---|
| ✅ | ✅ | **Ideal.** Ao vivo; cai no replay se a cota estourar. |
| ❌ | ✅ | Replay auditado nas perguntas curadas; resposta direta nas demais cobertas. |
| ✅ | ❌ | Ao vivo; cai na resposta direta se a cota estourar. |
| ❌ | ❌ | Resposta direta sobre headline, composição, difusão, núcleos, regime e itens. |

---

## Segurança (já garantido pelo código)

- Chave só em `.env` (local) ou Secrets (deploy) — **nunca no repositório**;
  `scripts/check_no_secrets.py` roda no CI.
- Injeção e fora-de-escopo são barrados **antes** do modelo; previsão de
  Copom/Selic e recomendação de ativo são barradas **na saída**.
- A resposta do modelo é renderizada como **texto inerte** (sem HTML), então uma
  resposta forjada não injeta nada na página.
- Todo número exibido é rastreável a uma evidência citada (expander "Evidências").
