"""Detect when a committed AI artifact (brief/replay) lags the latest data.

Pure, dependency-light helpers shared by the dashboard's brief guard and the
Q&A replay guard. The monthly refresh regenerates the AI artifacts alongside the
data so they stay in lockstep; these helpers are the safety net that keeps the
app from ever *showing* an AI artifact whose reference month trails the data
(a rare partial-refresh state). "Unknown month" never counts as stale — we only
hide on a confirmed mismatch.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Accept the product title and the legacy artifact title during the migration.
_BRIEF_MONTH_RE = re.compile(
    r"#\s*(?:Análise OpenIPCA|Brief de IA)\s*[—-]\s*IPCA\s*(\d{4}-\d{2})"
)
_LEGACY_TITLE_RE = re.compile(
    r"^#\s*Brief de IA\s*[—-]\s*IPCA\s*(\d{4}-\d{2})\s*$",
    flags=re.MULTILINE,
)
_LEGACY_MODE_RE = re.compile(r"^_AI Replay Mode[^\n]*_\s*\n?", flags=re.MULTILINE)


def normalize_analysis_title(markdown: str) -> str:
    """Present legacy artifacts with product-first, reader-facing copy."""
    normalized = _LEGACY_TITLE_RE.sub(
        lambda match: f"# Análise OpenIPCA — IPCA {match.group(1)}",
        markdown,
        count=1,
    )
    return _LEGACY_MODE_RE.sub("", normalized, count=1)


def reference_month_from_brief(reports_dir: Path) -> str | None:
    """Reference month of the committed brief: from metadata.json, else its H1."""
    meta_path = reports_dir / "metadata.json"
    if meta_path.exists():
        try:
            month = json.loads(meta_path.read_text(encoding="utf-8")).get("reference_month")
            if month:
                return str(month)
        except (ValueError, OSError):
            pass
    brief_path = reports_dir / "ai_brief.md"
    if brief_path.exists():
        try:
            match = _BRIEF_MONTH_RE.search(brief_path.read_text(encoding="utf-8"))
        except OSError:
            return None
        if match:
            return match.group(1)
    return None


def is_stale(artifact_month: str | None, data_month: str | None) -> bool:
    """True only when both months are known AND differ (unknown != stale)."""
    return bool(artifact_month and data_month and artifact_month != data_month)
