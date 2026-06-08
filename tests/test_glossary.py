"""Glossary tests — plain-language definitions for the executive panel.

These assert coverage and tolerant lookup, not exact wording (the wording is
owned/reviewed by Bruno).
"""

from ipca_dashboard.glossary import (
    CARD_TERMS,
    CORE_TERMS,
    METRIC_LABELS,
    describe,
    metric_label,
)

CARD_KEYS = [
    "IPCA m/m",
    "IPCA 12m",
    "IPCA MM3M",
    "Média núcleos MM3M",
    "Difusão MM3M",
    "Alertas ativos",
]

CORE_CODES = ["EX0", "EX1", "EX2", "EX3", "EX_FE", "DP", "MA", "MS", "P55"]


def test_every_card_has_a_definition():
    for key in CARD_KEYS:
        assert describe(key), f"missing glossary for card {key!r}"
        assert key in CARD_TERMS


def test_every_core_code_has_a_definition():
    for code in CORE_CODES:
        assert describe(code), f"missing glossary for core {code!r}"
        assert code in CORE_TERMS


def test_lookup_is_accent_and_case_insensitive():
    assert describe("difusão") == describe("difusao") == describe("DIFUSAO")
    assert describe("Difusão MM3M") == describe("difusao mm3m")


def test_concepts_are_present():
    for key in ("difusao", "nucleos", "mm3m", "regime", "alertas"):
        assert describe(key), f"missing concept {key!r}"


def test_decomposition_concepts_are_present():
    # The decomposition page surfaces variation (%), contribution (p.p.) and weight;
    # each needs a plain-language entry (also feeds the in-app glossary expander).
    for key in ("variacao", "contribuicao", "peso"):
        assert describe(key), f"missing concept {key!r}"
    # accented / cased variants resolve to the same definition
    assert describe("Variação") == describe("variacao")
    assert describe("Contribuição") == describe("contribuicao")
    # the definition spells out the relationship between the two units
    assert "peso" in describe("contribuicao").lower()


def test_unknown_term_returns_empty_string():
    assert describe("termo inexistente xyz") == ""
    assert describe("") == ""


def test_metric_label_friendly_for_known_keys_and_falls_back():
    for key in ("mom", "rolling_12m", "moving_average_3m", "three_month_saar"):
        assert metric_label(key) == METRIC_LABELS[key]
        assert "_" not in metric_label(key)  # no raw underscores reach the user
    assert metric_label("unknown_key") == "unknown_key"  # graceful fallback
