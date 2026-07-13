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


def normalize_evidence_ids(value: object) -> list[str]:
    """Evidence ids as a list, preserving malformed scalar ids as visible ids."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def resolve_claim_evidence(
    claims: list[dict], evidence: list[dict]
) -> list[dict[str, object]]:
    """Join each claim with its resolved evidence rows, for human-readable display.

    The UI promise is "every number traces to an official figure" — an evidence_id
    alone is unreadable; this returns one row per (claim, evidence_id) with the
    resolved metric/value/unit/date/source. A claim without ids still yields one
    row, and an unknown id resolves to a visible placeholder — a citation is
    never silently dropped.
    """
    by_id: dict[str, dict] = {}
    for item in evidence or []:
        if isinstance(item, dict) and item.get("evidence_id"):
            by_id[str(item["evidence_id"])] = item
    rows: list[dict[str, object]] = []
    for claim in claims or []:
        if not isinstance(claim, dict):
            continue
        text = str(claim.get("text", ""))
        ids = normalize_evidence_ids(claim.get("evidence_ids"))
        if not ids:
            rows.append(
                {
                    "claim": text,
                    "evidence_id": "",
                    "metric": "(sem evidence_id)",
                    "value": "",
                    "unit": "",
                    "date": "",
                    "source": "",
                }
            )
            continue
        for evidence_id in ids:
            item = by_id.get(evidence_id)
            if item is None:
                rows.append(
                    {
                        "claim": text,
                        "evidence_id": evidence_id,
                        "metric": f"({evidence_id} não encontrada)",
                        "value": "",
                        "unit": "",
                        "date": "",
                        "source": "",
                    }
                )
                continue
            rows.append(
                {
                    "claim": text,
                    "evidence_id": evidence_id,
                    "metric": str(item.get("metric", "")),
                    "value": item.get("value", ""),
                    "unit": str(item.get("unit", "")),
                    "date": str(item.get("date", "")),
                    "source": str(item.get("source", "")),
                }
            )
    return rows
