"""NoAIProvider: always-available, key-free, deterministic fallback.

Used in CI and whenever AI is disabled or a hosted provider fails. It does not
invent anything: it emits a minimal, fully grounded brief built straight from
the evidence table, so it always passes the guardrails.
"""

from __future__ import annotations


class NoAIProvider:
    name = "no_ai"
    capabilities: set[str] = set()  # no text/structured/tools — pure fallback

    def generate_structured(
        self,
        messages: list[dict],
        schema: dict,
        *,
        temperature: float = 0.0,
    ) -> dict:
        """Build a grounded brief from the evidence passed in `messages`.

        Convention: the caller puts the evidence table under a message
        {"role": "evidence", "content": [<evidence dicts>]}.
        """
        evidence = next(
            (m["content"] for m in messages if m.get("role") == "evidence"), []
        )
        by_id = {e["evidence_id"]: e for e in evidence}
        claims: list[dict] = []

        regime = by_id.get("ev_regime")
        if regime is not None:
            claims.append(
                {
                    "text": f"Regime inflacionário: {regime['value']}.",
                    "type": "regime",
                    "evidence_ids": ["ev_regime"],
                    "rule_id": regime.get("interpretation", "regime_v1"),
                }
            )
        for ev_id in ("ev_headline_mom", "ev_headline_12m", "ev_diffusion_mm3"):
            ev = by_id.get(ev_id)
            if ev is not None and ev.get("value") is not None:
                claims.append(
                    {
                        "text": f"{ev['metric']}: {ev['value']}{ev['unit']}.",
                        "type": "number",
                        "evidence_ids": [ev_id],
                    }
                )

        short = "Leitura determinística do IPCA a partir das fontes oficiais."
        if regime is not None:
            short = f"{short} Regime: {regime['value']}."
        return {
            "claims": claims,
            "short_brief": short,
            "monetary_policy_tone": "cautious",
            "investment_advice": False,
        }
