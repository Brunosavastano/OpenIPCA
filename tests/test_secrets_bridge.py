"""Tests for the Streamlit-secrets -> os.environ bridge.

On a deploy the AI key is a *secret*; the AI config reads os.environ. Without
the bridge the deploy key is invisible and the AI never activates. These pin the
contract: known keys are copied, real env vars always win, hostile/empty values
are ignored, and it never raises.
"""

import os

import pytest

from ipca_dashboard.ai.config import load_ai_config
from ipca_dashboard.ai.env import _AI_ENV_KEYS, bridge_secrets_to_env

pytestmark = pytest.mark.ai_contract


@pytest.fixture(autouse=True)
def _isolate_ai_env():
    """Clear the AI env keys for each test and restore the real values after."""
    saved = {key: os.environ.get(key) for key in _AI_ENV_KEYS}
    for key in _AI_ENV_KEYS:
        os.environ.pop(key, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_bridges_missing_keys_into_environ():
    n = bridge_secrets_to_env({"GOOGLE_API_KEY": "k", "OPENIPCA_AI_ENABLED": "true"})
    assert n == 2
    assert os.environ["GOOGLE_API_KEY"] == "k"
    assert os.environ["OPENIPCA_AI_ENABLED"] == "true"


def test_real_environment_variable_wins():
    os.environ["GOOGLE_API_KEY"] = "real-shell-value"
    n = bridge_secrets_to_env({"GOOGLE_API_KEY": "secret-value"})
    assert n == 0
    assert os.environ["GOOGLE_API_KEY"] == "real-shell-value"  # not clobbered


def test_ignores_none_and_blank_values():
    n = bridge_secrets_to_env({"GOOGLE_API_KEY": None, "OPENAI_API_KEY": "   "})
    assert n == 0
    assert "GOOGLE_API_KEY" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ


def test_none_secrets_is_noop():
    assert bridge_secrets_to_env(None) == 0


def test_boolean_secret_is_stringified():
    # TOML `OPENIPCA_AI_ENABLED = true` arrives as a bool; load_ai_config lowercases
    bridge_secrets_to_env({"OPENIPCA_AI_ENABLED": True})
    assert os.environ["OPENIPCA_AI_ENABLED"] == "true"
    assert os.environ["OPENIPCA_AI_ENABLED"].lower() in {"1", "true", "yes"}


def test_false_boolean_secret_does_not_activate_ai():
    bridge_secrets_to_env({"OPENIPCA_AI_ENABLED": False})
    assert os.environ["OPENIPCA_AI_ENABLED"] == "false"
    assert load_ai_config().enabled is False


def test_numeric_secret_values_are_ignored_not_stringified():
    n = bridge_secrets_to_env({"OPENIPCA_AI_ENABLED": 1, "GOOGLE_API_KEY": 12345})
    assert n == 0
    assert "OPENIPCA_AI_ENABLED" not in os.environ
    assert "GOOGLE_API_KEY" not in os.environ
    assert load_ai_config().enabled is False


def test_only_known_keys_are_bridged():
    n = bridge_secrets_to_env({"EVIL_KEY": "x", "PATH": "/tmp"})
    assert n == 0
    assert "EVIL_KEY" not in os.environ


def test_bridge_does_not_print_or_log_secret(capsys, caplog):
    secret = "redaction-test-secret-value"
    bridge_secrets_to_env({"GOOGLE_API_KEY": secret})
    captured = capsys.readouterr()
    assert secret not in captured.out
    assert secret not in captured.err
    assert secret not in caplog.text


def test_never_raises_on_hostile_secrets():
    class _Hostile:
        def __contains__(self, key):
            raise RuntimeError("boom")

        def __getitem__(self, key):
            raise RuntimeError("boom")

    assert bridge_secrets_to_env(_Hostile()) == 0  # swallowed, no crash
