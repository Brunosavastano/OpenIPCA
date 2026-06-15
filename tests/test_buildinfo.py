"""build_stamp: the deploy marker must be best-effort and never raise."""

from ipca_dashboard.buildinfo import build_stamp


def test_build_stamp_returns_a_string():
    # Inside the repo (git available in CI) this is "<sha> · <date>"; either way
    # it is always a string and never raises.
    assert isinstance(build_stamp(), str)


def test_build_stamp_is_empty_outside_a_git_repo(tmp_path):
    # A non-git directory must degrade to "" (no crash), so the footer is omitted.
    assert build_stamp(root=tmp_path) == ""
