"""Optional .env autoload for BYOK convenience (spec_V3 §3.4).

A user enables AI by creating a .env (git-ignored) and running the app — no
shell juggling. This is best-effort and safe:

- If python-dotenv isn't installed, it degrades silently (the app still works;
  env vars can be set the normal way). dotenv is an optional [ai] dependency.
- It NEVER overrides a variable already set in the real environment
  (override=False), so CI / deploy secrets always win over a stray .env.
- It loads the project-root .env only. No key is logged.
"""

from __future__ import annotations

from pathlib import Path

# project root = .../src/ipca_dashboard/ai/env.py -> parents[3]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_loaded = False


def load_env_once() -> bool:
    """Load the project-root .env if python-dotenv is available. Idempotent.

    Returns True if a .env was loaded, False otherwise (missing dep / no file /
    already loaded). Never raises.
    """
    global _loaded
    if _loaded:
        return False
    _loaded = True
    try:
        from dotenv import load_dotenv  # type: ignore
    except ImportError:
        return False
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return False
    # override=False: real environment variables take precedence over the file.
    return bool(load_dotenv(dotenv_path=env_path, override=False))
