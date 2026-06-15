"""build_stamp: the deploy marker must be best-effort and never raise."""

import subprocess

from ipca_dashboard import buildinfo
from ipca_dashboard.buildinfo import build_stamp


def test_build_stamp_returns_a_string():
    # Inside the repo (git available in CI) this is "<sha> · <date>"; either way
    # it is always a string and never raises.
    assert isinstance(build_stamp(), str)


def test_build_stamp_is_empty_outside_a_git_repo(tmp_path):
    # A non-git directory must degrade to "" (no crash), so the footer is omitted.
    assert build_stamp(root=tmp_path) == ""


def test_build_stamp_uses_only_short_sha_and_date(monkeypatch, tmp_path):
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        stdout = "abc1234\n" if "rev-parse" in args else "2026-06-15\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(buildinfo.subprocess, "run", fake_run)
    assert build_stamp(root=tmp_path) == "abc1234 · 2026-06-15"
    assert len(calls) == 2
    assert all(kwargs["timeout"] == 3 for _, kwargs in calls)


def test_build_stamp_is_empty_on_git_failure(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(args, 128, stdout="not a repo", stderr="fatal")

    monkeypatch.setattr(buildinfo.subprocess, "run", fake_run)
    assert build_stamp(root=tmp_path) == ""


def test_build_stamp_is_empty_on_timeout(monkeypatch, tmp_path):
    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, timeout=kwargs["timeout"])

    monkeypatch.setattr(buildinfo.subprocess, "run", fake_run)
    assert build_stamp(root=tmp_path) == ""
