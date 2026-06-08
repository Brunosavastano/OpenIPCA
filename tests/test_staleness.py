"""Unit tests for the AI-artifact staleness helpers (pure, no Streamlit/network)."""

from __future__ import annotations

import json

from ipca_dashboard.ai.staleness import is_stale, reference_month_from_brief


def test_reference_month_prefers_metadata(tmp_path):
    (tmp_path / "metadata.json").write_text(
        json.dumps({"reference_month": "2026-04"}), encoding="utf-8"
    )
    # H1 says a different month; metadata.json must win.
    (tmp_path / "ai_brief.md").write_text("# Brief de IA — IPCA 2025-01\n", encoding="utf-8")
    assert reference_month_from_brief(tmp_path) == "2026-04"


def test_reference_month_falls_back_to_h1_em_dash(tmp_path):
    (tmp_path / "metadata.json").write_text(json.dumps({"mode": "ai"}), encoding="utf-8")
    (tmp_path / "ai_brief.md").write_text("# Brief de IA — IPCA 2026-04\n\ntexto", encoding="utf-8")
    assert reference_month_from_brief(tmp_path) == "2026-04"


def test_reference_month_h1_hyphen_variant(tmp_path):
    (tmp_path / "ai_brief.md").write_text("# Brief de IA - IPCA 2026-05\n", encoding="utf-8")
    assert reference_month_from_brief(tmp_path) == "2026-05"


def test_reference_month_none_when_absent(tmp_path):
    assert reference_month_from_brief(tmp_path) is None


def test_is_stale_only_on_known_mismatch():
    assert is_stale("2026-03", "2026-04") is True
    assert is_stale("2026-04", "2026-04") is False
    assert is_stale(None, "2026-04") is False  # unknown artifact month
    assert is_stale("2026-04", None) is False  # unknown data month
    assert is_stale(None, None) is False
    assert is_stale("", "2026-04") is False
