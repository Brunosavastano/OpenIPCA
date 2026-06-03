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

import os
from pathlib import Path

# project root = .../src/ipca_dashboard/ai/env.py -> parents[3]
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_loaded = False

# The env vars the os.environ-based AI config reads. On a Streamlit deploy the
# operator sets these as *secrets* (st.secrets), but Streamlit does not reliably
# export secrets as environment variables — so bridge_secrets_to_env copies them,
# making the deploy key actually activate the AI. Real env vars always win.
_AI_ENV_KEYS = (
    "OPENIPCA_AI_ENABLED",
    "OPENIPCA_AI_PROVIDER",
    "OPENIPCA_AI_MODEL",
    "GEMINI_MODEL",
    "GOOGLE_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


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
    except Exception:
        return False
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return False
    # override=False: real environment variables take precedence over the file.
    try:
        return bool(load_dotenv(dotenv_path=env_path, override=False))
    except Exception:
        return False


def bridge_secrets_to_env(secrets: object) -> int:
    """Copy known AI keys from a Streamlit-secrets-like mapping into os.environ.

    Needed on deploys (e.g. Streamlit Community Cloud) where the key is set as a
    *secret*: the app reads os.environ, so without this the deploy key would be
    invisible and the AI would never activate. Real environment variables win
    (os.environ.setdefault), so a .env or shell value is never clobbered. A
    boolean secret (TOML `true`) is stringified, which load_ai_config accepts.

    Best-effort and never raises: a missing secrets store (no secrets.toml) or an
    odd value is ignored. Returns the number of keys bridged.
    """
    if secrets is None:
        return 0
    bridged = 0
    for key in _AI_ENV_KEYS:
        try:
            if key not in secrets:
                continue
            value = secrets[key]
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            before = os.environ.get(key)
            os.environ.setdefault(key, text)
            if before is None:
                bridged += 1
        except Exception:
            continue
    return bridged
