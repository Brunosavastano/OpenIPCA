"""Reference corpus loader: official IPCA facts as citable Evidence.

Guards the contract the Q&A grounding depends on: every fact is attributable
(id + source + prose), numeric facts carry their figure in `value` (so a claim
can cite it without a guardrail change), and a missing/malformed corpus degrades
to an empty list instead of breaking the Q&A.
"""

from ipca_dashboard.ai import reference
from ipca_dashboard.ai.evidence import Evidence
from ipca_dashboard.ai.reference import load_reference_evidence


def test_loads_real_corpus_with_attributable_facts():
    facts = load_reference_evidence()
    assert len(facts) >= 20  # the curated corpus
    assert all(isinstance(f, Evidence) for f in facts)
    for f in facts:
        assert f.evidence_id.startswith("ev_ref_")
        assert f.source  # a reference MUST be sourced
        assert f.interpretation  # ...and described
    ids = [f.evidence_id for f in facts]
    assert len(ids) == len(set(ids))  # unique ids


def test_numeric_facts_carry_their_figure_in_value():
    # The "no guardrail change" rule: figures the model will quote are citable values.
    by_id = {f.evidence_id: f for f in load_reference_evidence()}
    assert by_id["ev_ref_cobertura"].value == 16
    assert by_id["ev_ref_grupos"].value == 9


def test_missing_corpus_yields_empty(monkeypatch):
    def boom(name):
        raise FileNotFoundError(name)

    monkeypatch.setattr(reference, "load_yaml", boom)
    assert load_reference_evidence() == []


def test_malformed_corpus_yields_empty(monkeypatch):
    monkeypatch.setattr(reference, "load_yaml", lambda name: ["not", "a", "dict"])
    assert load_reference_evidence() == []
    monkeypatch.setattr(reference, "load_yaml", lambda name: {"facts": "nope"})
    assert load_reference_evidence() == []


def test_fact_without_id_source_or_interpretation_is_skipped(monkeypatch):
    monkeypatch.setattr(
        reference,
        "load_yaml",
        lambda name: {
            "facts": [
                {"id": "ev_ref_ok", "source": "http://x", "interpretation": "fato"},
                {"id": "ev_ref_no_source", "interpretation": "sem fonte"},
                {"id": "ev_ref_no_interp", "source": "http://x"},
                {"source": "http://x", "interpretation": "sem id"},
            ]
        },
    )
    assert [f.evidence_id for f in load_reference_evidence()] == ["ev_ref_ok"]


def test_non_scalar_value_is_dropped_to_none(monkeypatch):
    monkeypatch.setattr(
        reference,
        "load_yaml",
        lambda name: {
            "facts": [
                {"id": "ev_ref_list", "source": "h", "interpretation": "y", "value": [1, 2]},
                {"id": "ev_ref_bool", "source": "h", "interpretation": "y", "value": True},
                {"id": "ev_ref_num", "source": "h", "interpretation": "y", "value": 16},
            ]
        },
    )
    by_id = {f.evidence_id: f for f in load_reference_evidence()}
    assert by_id["ev_ref_list"].value is None
    assert by_id["ev_ref_bool"].value is None  # bool is not a valid figure
    assert by_id["ev_ref_num"].value == 16
