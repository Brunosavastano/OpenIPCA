import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_no_secrets.py"
SPEC = importlib.util.spec_from_file_location("check_no_secrets", SCRIPT_PATH)
check_no_secrets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_no_secrets)


def _matches_key_pattern(value: str) -> bool:
    return any(pattern.search(value) for pattern in check_no_secrets.KEY_PATTERNS)


def test_key_patterns_cover_provider_key_value_shapes():
    assert _matches_key_pattern("sk-" + ("A" * 24))
    assert _matches_key_pattern("sk-" + "proj-" + ("B" * 24))
    assert _matches_key_pattern("sk-" + "ant-" + ("C" * 24))


def test_key_patterns_do_not_match_key_names_or_short_placeholders():
    assert not _matches_key_pattern("OPENAI_API_KEY")
    assert not _matches_key_pattern("ANTHROPIC_API_KEY")
    assert not _matches_key_pattern("sk-short")


def test_forbidden_tracked_files_cover_real_secret_variants():
    forbidden = check_no_secrets.is_forbidden_tracked_file

    assert forbidden(".env")
    assert forbidden(".env.local")
    assert forbidden(".streamlit/secrets.toml")
    assert forbidden(".streamlit/secrets.toml.local")

    assert not forbidden(".env.example")
    assert not forbidden(".streamlit/secrets.toml.example")
