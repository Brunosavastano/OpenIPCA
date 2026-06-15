"""Build stamp: a glanceable 'what's deployed' marker for the app footer.

Streamlit Community Cloud deploys from a git clone, so HEAD == the live code.
Showing the short commit + date doubles as an auto-deploy indicator (it changes
the moment a new commit goes live) and a permanent "is the deploy current?" check.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def build_stamp(root: Path | str | None = None) -> str:
    """Return ``"<short-sha> · <date>"`` of the checkout, or ``""`` (best-effort).

    Reads the git HEAD of the repo the app runs from. Never raises: if git or the
    ``.git`` directory is missing (e.g. a non-git deploy), it returns an empty
    string so the caller can simply omit the footer.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
        date = subprocess.run(
            ["git", "log", "-1", "--format=%cs"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=3,
        ).stdout.strip()
    except Exception:  # noqa: BLE001 - a missing/!git environment must never break the app
        return ""
    if not sha:
        return ""
    return f"{sha} · {date}" if date else sha
