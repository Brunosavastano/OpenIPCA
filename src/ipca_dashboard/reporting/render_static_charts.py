"""Best-effort static PNG charts via Plotly + kaleido (optional, local only).

kaleido is an optional [report] dependency and is intentionally NOT in CI. If it
is unavailable, render_hero() returns None and the caller falls back to a manual
screenshot — the report never blocks on this.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

import pandas as pd

from ipca_dashboard.charts import diffusion_line, stacked_contribution

LOGGER = logging.getLogger(__name__)

# kaleido's write_image can hang (not just fail) on some platforms; bound it.
_WRITE_TIMEOUT_S = 30


def _write_png(fig, path: Path) -> str | None:
    def _do() -> None:
        fig.write_image(str(path), width=1200, height=675, scale=2)

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(_do).result(timeout=_WRITE_TIMEOUT_S)
        return path.name
    except FuturesTimeout:
        LOGGER.warning("Static chart timed out after %ss (kaleido); skipping.", _WRITE_TIMEOUT_S)
        return None
    except Exception as exc:  # noqa: BLE001 - PNG is best-effort
        LOGGER.warning("Static chart skipped (kaleido unavailable?): %s", exc)
        return None


def render_hero(bcb: pd.DataFrame, ipca_items: pd.DataFrame, out_dir: Path) -> list[str]:
    """Render hero charts to out_dir/charts; return embedded relative paths.

    Returns [] if kaleido is unavailable — the Markdown report still builds.
    """
    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    embedded: list[str] = []

    if not ipca_items.empty:
        name = _write_png(stacked_contribution(ipca_items), charts_dir / "01_decomposition.png")
        if name:
            embedded.append(f"charts/{name}")
    if not bcb.empty:
        name = _write_png(diffusion_line(bcb), charts_dir / "02_diffusion.png")
        if name:
            embedded.append(f"charts/{name}")
    return embedded
