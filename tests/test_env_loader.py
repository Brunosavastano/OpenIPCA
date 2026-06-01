"""Tests for the optional .env autoload — no real .env, no network.

Verifies graceful degradation without python-dotenv, that real env vars are
never overridden, and idempotency.
"""

import builtins
import importlib
import logging
import sys

import pytest

pytestmark = pytest.mark.ai_contract


def _fresh_module():
    sys.modules.pop("ipca_dashboard.ai.env", None)
    return importlib.import_module("ipca_dashboard.ai.env")


def test_load_env_degrades_silently_without_dotenv(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "dotenv" or name.startswith("dotenv."):
            raise ImportError("simulated: python-dotenv not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    env = _fresh_module()
    assert env.load_env_once() is False  # no crash, just no-op


def test_load_env_degrades_silently_when_dotenv_errors(monkeypatch, tmp_path):
    import types

    fake = types.ModuleType("dotenv")

    def broken_load_dotenv(dotenv_path=None, override=False):
        raise RuntimeError("broken dotenv parser")

    fake.load_dotenv = broken_load_dotenv
    monkeypatch.setitem(sys.modules, "dotenv", fake)

    env = _fresh_module()
    envfile = tmp_path / ".env"
    envfile.write_text("OPENAI_API_KEY=redaction-test-secret-value\n", encoding="utf-8")
    monkeypatch.setattr(env, "_PROJECT_ROOT", tmp_path)

    assert env.load_env_once() is False


def test_load_env_does_not_override_real_environment(monkeypatch, tmp_path):
    # A fake dotenv that records the override flag it was called with.
    import types

    captured = {}
    fake = types.ModuleType("dotenv")

    def fake_load_dotenv(dotenv_path=None, override=False):
        captured["override"] = override
        return True

    fake.load_dotenv = fake_load_dotenv
    monkeypatch.setitem(sys.modules, "dotenv", fake)

    env = _fresh_module()
    # Point the loader at an existing file so it proceeds to call load_dotenv.
    envfile = tmp_path / ".env"
    envfile.write_text("OPENIPCA_AI_ENABLED=true\n", encoding="utf-8")
    monkeypatch.setattr(env, "_PROJECT_ROOT", tmp_path)

    assert env.load_env_once() is True
    assert captured["override"] is False  # real env always wins


def test_load_env_does_not_log_secret_values(monkeypatch, tmp_path, caplog):
    import types

    secret = "redaction-test-secret-value"
    fake = types.ModuleType("dotenv")
    fake.load_dotenv = lambda dotenv_path=None, override=False: True
    monkeypatch.setitem(sys.modules, "dotenv", fake)
    monkeypatch.setenv("OPENAI_API_KEY", secret)

    env = _fresh_module()
    envfile = tmp_path / ".env"
    envfile.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
    monkeypatch.setattr(env, "_PROJECT_ROOT", tmp_path)

    with caplog.at_level(logging.DEBUG):
        assert env.load_env_once() is True
    assert secret not in caplog.text


def test_load_env_is_idempotent(monkeypatch, tmp_path):
    import types

    calls = {"n": 0}
    fake = types.ModuleType("dotenv")

    def fake_load_dotenv(dotenv_path=None, override=False):
        calls["n"] += 1
        return True

    fake.load_dotenv = fake_load_dotenv
    monkeypatch.setitem(sys.modules, "dotenv", fake)

    env = _fresh_module()
    envfile = tmp_path / ".env"
    envfile.write_text("X=1\n", encoding="utf-8")
    monkeypatch.setattr(env, "_PROJECT_ROOT", tmp_path)

    assert env.load_env_once() is True
    assert env.load_env_once() is False  # second call is a no-op
    assert calls["n"] == 1


def test_load_env_no_file_returns_false(monkeypatch, tmp_path):
    import types

    fake = types.ModuleType("dotenv")
    fake.load_dotenv = lambda dotenv_path=None, override=False: True
    monkeypatch.setitem(sys.modules, "dotenv", fake)

    env = _fresh_module()
    monkeypatch.setattr(env, "_PROJECT_ROOT", tmp_path)  # empty dir, no .env
    assert env.load_env_once() is False
