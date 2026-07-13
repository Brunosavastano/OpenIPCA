"""Best-effort static PNG charts via Plotly + kaleido.

kaleido is an optional [report] dependency and is intentionally NOT in CI. If it
is unavailable, render_hero() returns None and the caller falls back to a manual
screenshot — the report never blocks on this.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from ipca_dashboard.charts import diffusion_line, stacked_contribution

LOGGER = logging.getLogger(__name__)

# kaleido's write_image can hang (not just fail) on some platforms; bound it.
_WRITE_TIMEOUT_S = 30
_WRITE_IMAGE_CODE = """
from pathlib import Path
import sys

import plotly.io as pio

fig = pio.from_json(Path(sys.argv[1]).read_text(encoding="utf-8"))
fig.write_image(sys.argv[2], width=1200, height=675, scale=2)
"""


def _write_png(fig, path: Path) -> str | None:
    fig_json_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(fig.to_json())
            fig_json_path = Path(handle.name)
        completed = subprocess.run(
            [sys.executable, "-c", _WRITE_IMAGE_CODE, str(fig_json_path), str(path)],
            capture_output=True,
            text=True,
            timeout=_WRITE_TIMEOUT_S,
            check=False,
        )
        if completed.returncode == 0:
            return path.name
        detail = (
            completed.stderr or completed.stdout or f"exit code {completed.returncode}"
        ).strip()
        LOGGER.warning("Static chart skipped (kaleido unavailable?): %s", detail)
        return None
    except subprocess.TimeoutExpired:
        LOGGER.warning("Static chart timed out after %ss (kaleido); skipping.", _WRITE_TIMEOUT_S)
        return None
    except Exception as exc:  # noqa: BLE001 - PNG is best-effort
        LOGGER.warning("Static chart skipped (kaleido unavailable?): %s", exc)
        return None
    finally:
        if fig_json_path is not None:
            fig_json_path.unlink(missing_ok=True)


def render_hero(bcb: pd.DataFrame, ipca_items: pd.DataFrame, out_dir: Path) -> list[str]:
    """Render hero charts to out_dir/charts; return embedded relative paths.

    Returns [] if kaleido is unavailable — the Markdown report still builds.
    """
    charts_dir = out_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    embedded: list[str] = []

    if not ipca_items.empty:
        name = _write_png(stacked_contribution(ipca_items), out_dir / "report.png")
        if name:
            embedded.append(name)
    if not bcb.empty:
        name = _write_png(diffusion_line(bcb), charts_dir / "02_diffusion.png")
        if name:
            embedded.append(f"charts/{name}")
    return embedded
