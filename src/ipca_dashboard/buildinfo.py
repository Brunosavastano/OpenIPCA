"""Build stamp: a glanceable 'what's deployed' marker for the app footer.

Streamlit Community Cloud deploys from a git clone, so HEAD == the live code.
Showing the short commit + date doubles as an auto-deploy indicator (it changes
the moment a new commit goes live) and a permanent "is the deploy current?" check.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
import re


_SHORT_SHA_RE = re.compile(r"^[0-9a-f]{7,12}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _git_stdout(args: list[str], base: Path) -> str:
    result = subprocess.run(
        args,
        cwd=str(base),
        capture_output=True,
        text=True,
        timeout=3,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def build_stamp(root: Path | str | None = None) -> str:
    """Return ``"<short-sha> · <date>"`` of the checkout, or ``""`` (best-effort).

    Reads the git HEAD of the repo the app runs from. Never raises: if git or the
    ``.git`` directory is missing (e.g. a non-git deploy), it returns an empty
    string so the caller can simply omit the footer.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    try:
        sha = _git_stdout(["git", "rev-parse", "--short", "HEAD"], base)
        date = _git_stdout(["git", "log", "-1", "--format=%cs"], base)
    except Exception:  # noqa: BLE001 - a missing/!git environment must never break the app
        return ""
    if not _SHORT_SHA_RE.fullmatch(sha) or not _DATE_RE.fullmatch(date):
        return ""
    return f"{sha} · {date}"
