"""Evidence: the only facts the AI layer is allowed to cite.

An Evidence item is a single deterministic fact produced by the Tool API
(spec_V3 §3.2/§3.3). Every tool result IS an evidence item — there is no
separate "number" concept the model can invent. Claims must reference an
evidence_id that exists here, or guardrails reject them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    metric: str
    value: float | str | None
    unit: str
    date: str
    source: str
    interpretation: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def evidence_table_to_dicts(table: list[Evidence]) -> list[dict[str, object]]:
    return [e.to_dict() for e in table]


def evidence_ids(table: list[Evidence]) -> set[str]:
    return {e.evidence_id for e in table}
