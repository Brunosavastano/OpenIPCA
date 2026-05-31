"""Deterministic inflation-regime classifier (CP5).

Pure, rule-based classification consumed by the executive-page badge and, later,
by the AI layer (CP6) as grounded evidence. No AI, no randomness: same inputs ->
same regime + rule_id, always.

Signals (all percentiles are 0-100, mid-rank, from the deterministic pipeline):
- headline percentile (IPCA m/m vs its own expanding history)
- diffusion MM3M percentile
- core direction (MM3M vs 12m, when both available)

Spec_V3 §4 / §5.5.
"""

from __future__ import annotations

from dataclasses import dataclass

# Thresholds (percentile points). Kept explicit and few — spec_V3 §16 (lean v0.1).
LOW_P = 50.0   # at/below median = "low"
HIGH_P = 80.0  # at/above p80 = "high/broad"


@dataclass(frozen=True)
class RegimeResult:
    regime: str
    rule_id: str
    label_pt: str
    # evidence_ids are wired in CP6; kept here so the contract is stable now.
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "regime": self.regime,
            "rule_id": self.rule_id,
            "label_pt": self.label_pt,
            "evidence_ids": list(self.evidence_ids),
        }


REGIME_LABELS_PT: dict[str, str] = {
    "broad_disinflation": "Desinflação disseminada",
    "fragile_disinflation": "Desinflação frágil",
    "localized_shock": "Choque localizado",
    "broad_pressure": "Pressão disseminada",
    "mixed": "Quadro misto",
    "insufficient_data": "Dados insuficientes",
}


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and value == value  # not NaN


def classify_inflation_regime(context: dict) -> RegimeResult:
    """Classify the inflation regime from a context dict.

    Expected keys (any may be missing/None -> insufficient_data):
    - headline_percentile: float (IPCA m/m percentile)
    - diffusion_mm3_percentile: float
    Optional:
    - evidence_ids: list[str] to attach (CP6).

    Rules (first match wins):
    - headline<=p50 & diffusion<=p50            -> broad_disinflation
    - headline<=p50 & diffusion>=p80            -> fragile_disinflation
    - headline>=p80 & diffusion<=p50            -> localized_shock
    - headline>=p80 & diffusion>=p80            -> broad_pressure
    - otherwise                                 -> mixed
    """
    headline = context.get("headline_percentile")
    diffusion = context.get("diffusion_mm3_percentile")
    evidence_ids = tuple(context.get("evidence_ids", ()))

    if not _is_number(headline) or not _is_number(diffusion):
        return RegimeResult(
            "insufficient_data",
            "regime_v1_insufficient",
            REGIME_LABELS_PT["insufficient_data"],
            evidence_ids,
        )

    headline_low = headline <= LOW_P
    headline_high = headline >= HIGH_P
    diffusion_low = diffusion <= LOW_P
    diffusion_high = diffusion >= HIGH_P

    if headline_low and diffusion_low:
        regime, rule = "broad_disinflation", "regime_v1_headline_low_diffusion_low"
    elif headline_low and diffusion_high:
        regime, rule = "fragile_disinflation", "regime_v1_headline_low_diffusion_high"
    elif headline_high and diffusion_low:
        regime, rule = "localized_shock", "regime_v1_headline_high_diffusion_low"
    elif headline_high and diffusion_high:
        regime, rule = "broad_pressure", "regime_v1_headline_high_diffusion_high"
    else:
        regime, rule = "mixed", "regime_v1_mixed"

    return RegimeResult(regime, rule, REGIME_LABELS_PT[regime], evidence_ids)
