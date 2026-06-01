"""Build the shareable release report (spec_V3 §8).

Usage:
    python -m ipca_dashboard.reporting.build_report --latest

Reuses the deterministic diagnostic + regime and the pre-generated AI brief
(reports/latest/ai_brief.md) if present. Writes reports/latest/report.md and,
when kaleido is available, a hero PNG under reports/latest/charts/.
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ipca_dashboard.config import PROCESSED_DIR, PROJECT_ROOT
from ipca_dashboard.diagnostics import build_diagnostic_text
from ipca_dashboard.reporting.render_markdown import (
    load_ai_brief,
    render_report_markdown,
    write_metadata,
)

LOGGER = logging.getLogger(__name__)
REPORTS_LATEST = PROJECT_ROOT / "reports" / "latest"


def _load(name: str) -> pd.DataFrame:
    path = PROCESSED_DIR / name
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def build_report(
    out_dir: Path, *, generated_at: str = "", with_charts: bool = False
) -> dict[str, Path]:
    """Build report.md (+ hero PNG if with_charts) into out_dir. Returns paths.

    Charts are opt-in: kaleido's write_image can *hang* (not just fail) on some
    platforms, and a best-effort try/except cannot catch a hang. So the default
    path renders Markdown only (fast, robust); pass with_charts=True to attempt
    the hero PNG locally where kaleido is known to work.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    bcb = _load("bcb_series_monthly.parquet")
    items = _load("ipca_items_monthly.parquet")
    cores = _load("core_metrics_monthly.parquet")
    alerts = _load("alerts.parquet")
    if bcb.empty:
        raise SystemExit("No processed data found. Run the pipeline first.")

    diagnostic = build_diagnostic_text(bcb, items, cores, alerts)
    charts = []
    if with_charts:
        from ipca_dashboard.reporting.render_static_charts import render_hero

        charts = render_hero(bcb, items, out_dir)
    ai_brief_md = load_ai_brief(out_dir)
    markdown = render_report_markdown(bcb, diagnostic, ai_brief_md=ai_brief_md, charts=charts)

    paths = {"report": out_dir / "report.md"}
    paths["report"].write_text(markdown, encoding="utf-8")
    write_metadata(
        out_dir,
        {
            "generated_at": generated_at,
            "reference_month": diagnostic.get("reference_month", ""),
            "has_ai_brief": ai_brief_md is not None,
            "charts": charts,
            "hero_available": bool(charts),
        },
    )
    return paths


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build the shareable IPCA release report.")
    parser.add_argument("--latest", action="store_true", help="Build into reports/latest/.")
    parser.add_argument("--out", default=str(REPORTS_LATEST), help="Output directory.")
    parser.add_argument(
        "--with-charts",
        action="store_true",
        help="Also render the hero PNG via kaleido (local only; may be slow).",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()), format="%(levelname)s:%(message)s"
    )

    out_dir = REPORTS_LATEST if args.latest else Path(args.out)
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    paths = build_report(out_dir, generated_at=generated_at, with_charts=args.with_charts)
    LOGGER.info("Wrote report -> %s", paths["report"])
    if not args.with_charts:
        LOGGER.info("Hero PNG skipped (pass --with-charts to render it locally).")


if __name__ == "__main__":
    main()
