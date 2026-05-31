"""Fail if API keys or real secret files are committed to the repo.

Scans only git-tracked files (so local .env / data / venv are ignored) for
provider key *values*, and asserts that real secret files are not tracked.

Design note: this must distinguish a real leaked key from prose that merely
mentions a key's name (the spec and docs talk about OPENAI_API_KEY, sk-..., etc.).
So we match on key *value* shapes, and we skip example files and Markdown docs
for the value scan (they legitimately discuss key formats).

Usage:
    python scripts/check_no_secrets.py
Exit code 0 = clean, 1 = problem found. Used in CI.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Key *value* shapes. Deliberately specific to avoid flagging prose like
# "set OPENAI_API_KEY" — we require an actual key-looking token.
KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),   # Anthropic
    re.compile(r"sk-(?!ant-)[A-Za-z0-9_\-]{20,}"),  # OpenAI-style, incl. sk-proj-...
]

# Files exempt from the value scan: example templates and Markdown docs
# (they legitimately reference key names/formats).
ALLOWED_FILES = {".env.example", ".streamlit/secrets.toml.example"}
SKIP_SUFFIXES = {
    ".parquet", ".png", ".jpg", ".jpeg", ".gif", ".zip", ".ipynb", ".md",
}


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def is_forbidden_tracked_file(norm: str) -> bool:
    """Return True for real secret files; examples are allowed."""
    return (
        norm == ".env"
        or (norm.startswith(".env.") and norm != ".env.example")
        or norm == ".streamlit/secrets.toml"
        or (
            norm.startswith(".streamlit/secrets.toml.")
            and norm != ".streamlit/secrets.toml.example"
        )
    )


def main() -> int:
    problems: list[str] = []
    files = tracked_files()

    for rel in files:
        norm = rel.replace("\\", "/")
        if is_forbidden_tracked_file(norm):
            problems.append(f"Real secret file is tracked: {norm}")

    for rel in files:
        norm = rel.replace("\\", "/")
        if norm in ALLOWED_FILES or Path(norm).suffix.lower() in SKIP_SUFFIXES:
            continue
        try:
            text = Path(rel).read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError):
            continue
        for pattern in KEY_PATTERNS:
            if pattern.search(text):
                problems.append(f"Possible API key value in {norm} (pattern: {pattern.pattern})")
                break

    if problems:
        print("check_no_secrets: FAILED")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"check_no_secrets: OK ({len(files)} tracked files scanned)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
