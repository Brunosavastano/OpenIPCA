"""Human-readable evidence: claim→evidence resolution and the trace summary.

These power the "every number traces to an official figure" UI promise — the
expanders must show resolved metric/value/source, never raw ids only, and must
degrade silently (omit, not crash) on missing/malformed artifacts.
"""

import json
from pathlib import Path

from ipca_dashboard.ai.evidence import resolve_claim_evidence
from ipca_dashboard.ai.trace import brief_stamp_line, load_brief_metadata, load_trace_summary

EVIDENCE = [
    {
        "evidence_id": "ev_headline_mom",
        "metric": "IPCA m/m",
        "value": 0.67,
        "unit": "%",
        "date": "2026-04",
        "source": "BCB/SGS",
        "interpretation": "",
    },
    {
        "evidence_id": "ev_diffusion_mm3",
        "metric": "Difusão MM3M",
        "value": 64.63,
        "unit": "%",
        "date": "2026-04",
        "source": "BCB/SGS",
        "interpretation": "",
    },
]


def test_resolve_joins_each_claim_with_its_evidence_rows():
    claims = [
        {"text": "O IPCA subiu 0,67%.", "type": "number", "evidence_ids": ["ev_headline_mom"]},
        {
            "text": "A alta está espalhada.",
            "type": "interpretation",
            "evidence_ids": ["ev_headline_mom", "ev_diffusion_mm3"],
        },
    ]
    rows = resolve_claim_evidence(claims, EVIDENCE)
    assert len(rows) == 3  # 1 + 2 (one row per claim-evidence pair)
    assert rows[0]["metric"] == "IPCA m/m" and rows[0]["value"] == 0.67
    assert rows[0]["source"] == "BCB/SGS"
    assert {r["metric"] for r in rows[1:]} == {"IPCA m/m", "Difusão MM3M"}
    # the claim text rides along on every row
    assert rows[1]["claim"] == rows[2]["claim"] == "A alta está espalhada."


def test_resolve_never_silently_drops_a_citation():
    claims = [
        {"text": "Sem evidência.", "type": "interpretation", "evidence_ids": []},
        {"text": "Id órfão.", "type": "number", "evidence_ids": ["ev_inexistente"]},
    ]
    rows = resolve_claim_evidence(claims, EVIDENCE)
    assert len(rows) == 2  # both claims still visible
    assert rows[0]["metric"] == "(sem evidence_id)"  # no ids -> explicit placeholder
    assert "ev_inexistente" in rows[1]["metric"]  # unknown id -> visible placeholder


def test_resolve_treats_scalar_evidence_id_as_one_citation():
    claims = [{"text": "IPCA subiu.", "type": "number", "evidence_ids": "ev_headline_mom"}]
    rows = resolve_claim_evidence(claims, EVIDENCE)
    assert len(rows) == 1
    assert rows[0]["metric"] == "IPCA m/m"


def test_resolve_tolerates_malformed_inputs():
    assert resolve_claim_evidence([], []) == []
    assert resolve_claim_evidence(None, None) == []
    rows = resolve_claim_evidence(["not a dict"], [{"no_id": 1}, "junk"])
    assert rows == []


def test_trace_summary_reads_the_committed_shape(tmp_path: Path):
    trace = {
        "prompt_version": "release_brief_v1",
        "tool_calls": [{"tool": "get_headline"}, {"tool": "get_diffusion"}],
        "evidence_ids": ["ev_a", "ev_b", "ev_c"],
        "claims": [{"text": "IPCA subiu.", "type": "number", "evidence_ids": "ev_a"}],
        "used_fallback": False,
    }
    path = tmp_path / "ai_trace.json"
    path.write_text(json.dumps(trace), encoding="utf-8")
    summary = load_trace_summary(path)
    assert summary is not None
    assert summary["tools"] == ["get_headline", "get_diffusion"]
    assert summary["n_evidence"] == 3
    assert summary["claims"] == [{"text": "IPCA subiu.", "evidence_ids": ["ev_a"]}]


def test_trace_summary_is_none_for_missing_malformed_or_empty(tmp_path: Path):
    assert load_trace_summary(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_trace_summary(bad) is None
    not_dict = tmp_path / "list.json"
    not_dict.write_text("[1, 2]", encoding="utf-8")
    assert load_trace_summary(not_dict) is None
    empty = tmp_path / "empty.json"
    empty.write_text(json.dumps({"tool_calls": [], "claims": []}), encoding="utf-8")
    assert load_trace_summary(empty) is None


def test_trace_summary_against_the_real_committed_artifact():
    real = Path(__file__).resolve().parents[1] / "reports" / "latest" / "ai_trace.json"
    if not real.exists():  # CI checkout always has it, but stay robust
        return
    summary = load_trace_summary(real)
    assert summary is not None
    assert summary["tools"] and summary["claims"]
    assert all(claim["text"] for claim in summary["claims"])


def test_brief_metadata_loader_robustness(tmp_path: Path):
    assert load_brief_metadata(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert load_brief_metadata(bad) is None
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert load_brief_metadata(empty) is None
    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"provider": "openai"}), encoding="utf-8")
    assert load_brief_metadata(ok) == {"provider": "openai"}


def test_brief_stamp_line_formats_only_existing_fields():
    meta = {
        "generated_at": "2026-06-04T18:48:34+00:00",
        "provider": "openai",
        "prompt_version": "release_brief_v1",
        "prompt_hash": "sha256:c74d958f8534b0cd0a04e2387990e32f71aa64ad44d84e274646dbeadcdbd0b1",
        "evidence_hash": "sha256:7cc3487b8b3473fd4561be0ac66e3426a2cf353c307dcb433baebd4968226b01",
    }
    line = brief_stamp_line(meta)
    assert "Gerado em 2026-06-04" in line
    assert "provider openai" in line
    assert "prompt release_brief_v1 (sha256:c74d958f)" in line  # truncated, searchable
    assert "evidência sha256:7cc3487b" in line
    assert "dbeadcdbd0b1" not in line  # full hash does NOT flood the caption


def test_brief_stamp_line_degrades_to_empty_for_empty_meta():
    assert brief_stamp_line({}) == ""
    assert brief_stamp_line({"provider": "openai"}) == "provider openai"
