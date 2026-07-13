"""Stable URL and evidence-navigation contracts for the Streamlit app."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

PAGE_SLUGS = {
    "executivo": "Painel executivo",
    "pergunte": "Pergunte ao IPCA",
    "decomposicao": "Decomposição",
    "nucleos": "Núcleos",
    "difusao": "Difusão",
    "alertas": "Alertas",
    "metodologia": "Metodologia",
}
SLUG_BY_PAGE = {label: slug for slug, label in PAGE_SLUGS.items()}
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ITEM_EVIDENCE_RE = re.compile(r"^ev_(?:weight|item_(?:mom|12m|contrib))_(\d+)$")


@dataclass(frozen=True)
class NavigationTarget:
    view: str
    month: str = ""
    evidence: str = ""
    item: str = ""


def _scalar(value: object) -> str:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "")


def parse_query_params(params: Mapping[str, object]) -> NavigationTarget:
    """Validate public URL params; invalid values are ignored, never raised."""
    view = _scalar(params.get("view"))
    month = _scalar(params.get("month"))
    evidence = _scalar(params.get("evidence"))
    item = _scalar(params.get("item"))
    return NavigationTarget(
        view=view if view in PAGE_SLUGS else "",
        month=month if _MONTH_RE.fullmatch(month) else "",
        evidence=evidence if re.fullmatch(r"ev_[A-Za-z0-9_]+", evidence) else "",
        item=item if item.isdigit() else "",
    )


def target_for_evidence(evidence_id: object, evidence_date: object = "") -> NavigationTarget | None:
    """Map a deterministic evidence id to the panel that explains it."""
    evidence = str(evidence_id or "")
    month = str(evidence_date or "")
    month = month if _MONTH_RE.fullmatch(month) else ""
    item_match = _ITEM_EVIDENCE_RE.fullmatch(evidence)
    if item_match:
        return NavigationTarget("decomposicao", month, evidence, item_match.group(1))
    prefixes = (
        ("ev_headline_", "executivo"),
        ("ev_core_", "nucleos"),
        ("ev_diffusion_", "difusao"),
        ("ev_contrib_", "decomposicao"),
        ("ev_alert_", "alertas"),
        ("ev_ref_", "metodologia"),
    )
    for prefix, view in prefixes:
        if evidence.startswith(prefix):
            return NavigationTarget(view, month, evidence)
    if evidence == "ev_regime":
        return NavigationTarget("executivo", month, evidence)
    return None
