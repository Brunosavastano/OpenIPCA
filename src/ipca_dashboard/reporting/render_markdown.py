"""Render the shareable report as Markdown (pure, deterministic, no network).

This is the testable core of CP8. It reuses the deterministic diagnostic +
regime (the floor) and folds in the pre-generated AI brief artifact when present
(AI Replay Mode). It never calls a model or the network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DISCLAIMER = (
    "OpenIPCA é uma ferramenta de pesquisa e educação. Usa dados públicos e cálculos "
    "determinísticos. Não é recomendação de investimento, não prevê política monetária e "
    "pode conter erros. Não é afiliado ao IBGE nem ao Banco Central do Brasil."
)


def _fmt(value: object, suffix: str = "%") -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "n.d."
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}{suffix}"
    return str(value)


def _latest(bcb: pd.DataFrame, name: str) -> pd.Series | None:
    sub = bcb[bcb["series_short_name"] == name].sort_values("date")
    return sub.iloc[-1] if not sub.empty else None


def render_report_markdown(
    bcb: pd.DataFrame,
    diagnostic: dict,
    *,
    ai_brief_md: str | None = None,
    charts: list[str] | None = None,
) -> str:
    """Build the report Markdown from deterministic inputs.

    `diagnostic` is the dict from build_diagnostic_text (diagnostic/regime/...).
    `ai_brief_md` is the pre-generated AI brief markdown, if any.
    `charts` is an optional list of image paths to embed (hero first).
    """
    reference_month = diagnostic.get("reference_month", "")
    ipca = _latest(bcb, "IPCA")
    diffusion = _latest(bcb, "Difusao")

    lines: list[str] = []
    lines.append(f"# OpenIPCA — leitura do IPCA {reference_month}".rstrip())
    lines.append("")
    lines.append("_Brazilian inflation beyond the headline._")
    lines.append("")

    if charts:
        for path in charts:
            lines.append(f"![chart]({path})")
        lines.append("")

    lines.append("## Números do mês")
    lines.append("")
    if ipca is not None:
        lines.append(f"- **IPCA m/m:** {_fmt(ipca.get('mom'))}")
        lines.append(f"- **IPCA 12m:** {_fmt(ipca.get('rolling_12m'))}")
        lines.append(f"- **IPCA MM3M (NSA):** {_fmt(ipca.get('moving_average_3m'))}")
    if diffusion is not None:
        lines.append(f"- **Difusão MM3M:** {_fmt(diffusion.get('moving_average_3m'), '%')}")
    regime_label = diagnostic.get("regime_label")
    if regime_label:
        lines.append(f"- **Regime:** {regime_label}")
    lines.append("")

    lines.append("## Leitura determinística")
    lines.append("")
    lines.append(diagnostic.get("diagnostic", "Sem diagnóstico disponível."))
    lines.append("")

    if ai_brief_md:
        lines.append("## Leitura assistida por IA (AI Replay Mode)")
        lines.append("")
        lines.append(
            "_Pré-gerada e auditável: cada afirmação é rastreável a uma evidência. "
            "Sem chamada de IA ao vivo._"
        )
        lines.append("")
        lines.append(ai_brief_md.strip())
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Fontes:** IBGE/SIDRA 7060, BCB/SGS.")
    lines.append("")
    lines.append(f"> {DISCLAIMER}")
    return "\n".join(lines).strip() + "\n"


def load_ai_brief(reports_dir: Path) -> str | None:
    """Return the pre-generated AI brief markdown if it exists."""
    path = reports_dir / "ai_brief.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def load_reference_month(processed_dir: Path) -> str:
    path = processed_dir / "bcb_series_monthly.parquet"
    if not path.exists():
        return ""
    bcb = pd.read_parquet(path)
    if bcb.empty:
        return ""
    return pd.to_datetime(bcb["date"]).max().strftime("%Y-%m")


def write_metadata(reports_dir: Path, payload: dict) -> Path:
    path = reports_dir / "report_metadata.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
