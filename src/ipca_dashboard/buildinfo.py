"""Build stamp: a glanceable 'what's deployed' marker for the app footer.

Streamlit Community Cloud deploys from a git clone, so HEAD == the live code.
Showing the short commit + date doubles as an auto-deploy indicator (it changes
the moment a new commit goes live) and a permanent "is the deploy current?" check.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

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


def _sha_from_dotgit(base: Path) -> str:
    """Read the short commit SHA straight from ``.git`` — no git binary needed.

    Streamlit Cloud's app sandbox has **no git CLI on PATH**, but the ``.git`` dir
    is present (it powers "Pulling code changes"). ``HEAD`` is either a ref pointer
    (normal) or a raw SHA (detached); a ref resolves via ``refs/...`` (loose) or
    ``packed-refs``. Best-effort: returns ``""`` on anything unexpected.
    """
    git_dir = base / ".git"
    head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref:"):
        return head[:7]  # detached HEAD = raw SHA
    ref = head.split(":", 1)[1].strip()
    loose = git_dir / ref
    if loose.is_file():
        return loose.read_text(encoding="utf-8").strip()[:7]
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for raw in packed.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", "^")):
                continue
            sha, _, name = line.partition(" ")
            if name == ref:
                return sha[:7]
    return ""


def build_stamp(root: Path | str | None = None) -> str:
    """Return ``"<short-sha> · <date>"`` of the checkout, or ``""`` (best-effort).

    Prefers the git CLI (gives commit + date), which works locally. On Streamlit
    Cloud — where the app sandbox has no git binary — it falls back to reading
    ``.git/HEAD`` directly and shows the short SHA alone. Never raises: if neither
    path yields a valid SHA, it returns ``""`` so the caller omits the footer.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    try:
        sha = _git_stdout(["git", "rev-parse", "--short", "HEAD"], base)
        date = _git_stdout(["git", "log", "-1", "--format=%cs"], base)
    except Exception:  # noqa: BLE001 - a missing/!git environment must never break the app
        sha, date = "", ""
    if _SHORT_SHA_RE.fullmatch(sha) and _DATE_RE.fullmatch(date):
        return f"{sha} · {date}"
    # No git CLI (e.g. Streamlit Cloud) — read the SHA straight from .git.
    try:
        sha = _sha_from_dotgit(base)
    except Exception:  # noqa: BLE001 - a missing/unreadable .git must never break the app
        return ""
    return sha if _SHORT_SHA_RE.fullmatch(sha) else ""
