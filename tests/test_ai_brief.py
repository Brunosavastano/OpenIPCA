"""CP7 brief tests — pure, no network (fake providers only).

Covers: a grounded provider brief passes; ANY provider failure or guardrail
rejection falls back to the deterministic brief (AI never blocks the product);
artifacts (brief/trace/metadata) are written; model-agnostic (no vendor named).
"""

import json

import pandas as pd
import pytest

import ipca_dashboard.ai.brief as brief_module
from ipca_dashboard.ai.brief import (
    BriefResult,
    generate_brief,
    write_brief_artifacts,
)

pytestmark = pytest.mark.ai_contract


def _bcb() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {
                "date": date,
                "series_short_name": "IPCA",
                "mom": 0.30,
                "rolling_12m": 4.50,
                "moving_average_3m": 0.40,
                "percentile_since_2012": 35.0,
                "moving_average_3m_percentile": 30.0,
            },
            {
                "date": date,
                "series_short_name": "Difusao",
                "mom": 58.0,
                "rolling_12m": None,
                "moving_average_3m": 55.0,
                "percentile_since_2012": 40.0,
                "moving_average_3m_percentile": 45.0,
            },
        ]
    )


def _items() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {"date": date, "level": "group", "item_name": "Alimentação", "contribution_mom": 0.18},
            {"date": date, "level": "group", "item_name": "Transportes", "contribution_mom": -0.05},
        ]
    )


def _cores() -> pd.DataFrame:
    date = pd.Timestamp("2024-03-01")
    return pd.DataFrame(
        [
            {
                "date": date,
                "core_set_name": "bcb_compact",
                "core_name": "Média",
                "mom": 0.40,
                "moving_average_3m": 0.45,
                "is_complete": True,
            }
        ]
    )


class _GroundedProvider:
    """A fake provider that returns a valid, grounded brief (no network)."""

    name = "fake_grounded"
    capabilities = {"structured", "tools"}

    def generate_structured(self, messages, schema, *, temperature=0.0):
        evidence = next(m["content"] for m in messages if m["role"] == "evidence")
        ids = {e["evidence_id"] for e in evidence}
        claims = []
        if "ev_regime" in ids:
            reg = next(e for e in evidence if e["evidence_id"] == "ev_regime")
            claims.append(
                {
                    "text": f"Regime: {reg['value']}.",
                    "type": "regime",
                    "evidence_ids": ["ev_regime"],
                    "rule_id": reg["interpretation"],
                }
            )
        return {
            "claims": claims,
            "short_brief": "Leitura aterrada.",
            "monetary_policy_tone": "cautious",
            "investment_advice": False,
        }


class _BoomProvider:
    name = "fake_boom"
    capabilities = {"structured"}

    def generate_structured(self, messages, schema, *, temperature=0.0):
        raise RuntimeError("simulated provider outage")


class _UngroundedProvider:
    """Returns an ungrounded number -> must be caught by guardrails -> fallback."""

    name = "fake_ungrounded"
    capabilities = {"structured"}

    def generate_structured(self, messages, schema, *, temperature=0.0):
        return {
            "claims": [
                {"text": "IPCA foi 9.99%", "type": "number", "evidence_ids": ["ev_headline_mom"]}
            ],
            "short_brief": "x",
            "monetary_policy_tone": "cautious",
            "investment_advice": False,
        }


def _gen(provider):
    return generate_brief(_bcb(), _items(), _cores(), pd.DataFrame(), provider=provider)


def test_grounded_provider_brief_is_used():
    result = _gen(_GroundedProvider())
    assert isinstance(result, BriefResult)
    assert result.used_fallback is False
    assert result.provider_name == "fake_grounded"
    assert result.brief["claims"]


def test_provider_outage_falls_back_to_deterministic():
    result = _gen(_BoomProvider())
    assert result.used_fallback is True
    assert result.provider_name == "no_ai"
    assert result.error and "simulated provider outage" in result.error
    assert result.brief["investment_advice"] is False  # floor still valid


def test_guardrail_rejection_falls_back_to_deterministic():
    result = _gen(_UngroundedProvider())
    assert result.used_fallback is True
    assert result.provider_name == "no_ai"


def test_empty_data_never_raises_and_falls_back():
    result = generate_brief(
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
        provider=_GroundedProvider(),
    )
    assert result.used_fallback is True
    assert result.provider_name == "no_ai"
    assert result.error
    assert result.evidence == []


def test_broken_fallback_still_returns_minimal_brief(monkeypatch):
    class _BrokenNoAI:
        name = "broken_no_ai"
        capabilities = set()

        def generate_structured(self, messages, schema, *, temperature=0.0):
            raise RuntimeError("fallback failed")

    monkeypatch.setattr(brief_module, "NoAIProvider", _BrokenNoAI)

    result = _gen(_BoomProvider())
    assert result.used_fallback is True
    assert result.provider_name == "broken_no_ai"
    assert result.brief["claims"] == []
    assert "fallback failed" in result.error


def test_trace_links_tools_evidence_and_claims():
    result = _gen(_GroundedProvider())
    assert result.trace["tool_calls"]
    assert result.trace["evidence_ids"]
    assert "ev_regime" in result.trace["evidence_ids"]
    regime_claim = next(c for c in result.trace["claims"] if c["type"] == "regime")
    assert regime_claim["rule_id"] == "regime_v1_headline_low_diffusion_low"


def test_artifacts_are_written(tmp_path):
    result = _gen(_GroundedProvider())
    paths = write_brief_artifacts(result, tmp_path, reference_month="2024-03")
    assert paths["brief"].exists() and paths["trace"].exists() and paths["metadata"].exists()
    meta = json.loads(paths["metadata"].read_text(encoding="utf-8"))
    assert meta["schema_version"] == "brief_v1"
    assert meta["prompt_hash"].startswith("sha256:")
    assert meta["evidence_hash"].startswith("sha256:")
    brief_md = paths["brief"].read_text(encoding="utf-8")
    assert brief_md.startswith("# Análise OpenIPCA — IPCA 2024-03")
    assert "AI Replay Mode" in brief_md
    # Reading copy is clean: no per-claim evidence_ids leak into the prose...
    assert "evidência:" not in brief_md
    assert "ev_regime" not in brief_md
    # ...but full traceability is preserved in the trace.
    trace = json.loads(paths["trace"].read_text(encoding="utf-8"))
    assert trace["evidence_ids"]
    regime_claim = next(c for c in trace["claims"] if c["type"] == "regime")
    assert "rule_id" in regime_claim


def test_default_provider_resolution_is_offline_safe():
    # No provider passed, AI disabled by default -> NoAIProvider, no network.
    result = generate_brief(_bcb(), _items(), _cores(), pd.DataFrame())
    assert result.provider_name == "no_ai"
