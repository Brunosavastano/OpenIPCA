"""Deterministic eval battery for the Q&A — no model, no network (CI).

Locks the input-guardrail behavior (scope + injection) and the question-aware
item-evidence wiring against a curated, audited battery (see qa_eval_cases). This
is the regression net that replaces the manual live reproductions we kept doing
while building the Q&A (#68/#69/#70/#71).
"""

import pandas as pd
import pytest
from qa_eval_cases import EVIDENCE_CASES, INPUT_CASES

from ipca_dashboard.ai.guardrails import GuardrailError, check_question
from ipca_dashboard.ai.tools import get_item_changes, get_item_weights

pytestmark = pytest.mark.ai_contract


@pytest.mark.parametrize(
    "question,expected,category",
    INPUT_CASES,
    ids=[f"{c[2]}:{c[0][:32]}" for c in INPUT_CASES],
)
def test_input_guardrail(question, expected, category):
    if expected == "refused":
        with pytest.raises(GuardrailError):
            check_question(question)
    else:
        check_question(question)  # a legitimate question must NOT be refused


def _items_fixture() -> pd.DataFrame:
    date = pd.Timestamp("2026-05-01")
    rows = [
        ("3103001", "subitem", "Gasolina", 5.34, -1.46, 5.43, -0.08),
        ("1101001", "subitem", "Café moído", 0.59, -2.38, -12.25, -0.01),
        ("1101002", "subitem", "Arroz", 0.50, 1.74, -16.92, 0.01),
        ("5101010", "subitem", "Passagem aérea", 0.67, 3.10, 8.20, 0.02),
    ]
    return pd.DataFrame(
        [
            {"date": date, "classification_code": c, "level": lvl, "item_name": n,
             "weight": w, "mom": mom, "yoy": yoy, "contribution_mom": cm}
            for c, lvl, n, w, mom, yoy, cm in rows
        ]
    )


@pytest.mark.parametrize(
    "question,should_inject",
    EVIDENCE_CASES,
    ids=[c[0][:36] for c in EVIDENCE_CASES],
)
def test_named_item_evidence_injection(question, should_inject):
    items = _items_fixture()
    ev = get_item_weights(question, items) + get_item_changes(question, items)
    injected = any(e.evidence_id.startswith(("ev_weight_", "ev_item_")) for e in ev)
    assert injected is should_inject
