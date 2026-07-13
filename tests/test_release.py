import gzip
import json
from datetime import date

import pytest

from ipca_dashboard.release import (
    PERIODS_URL,
    ReleaseProbeError,
    _request_json,
    build_release_state,
    freshness_status,
    load_release_state,
    next_release_date,
    parse_latest_period,
    probe_release,
)


def _periods(latest: str = "202406") -> list[dict]:
    return [
        {"id": "202405", "modificacao": "11/06/2024"},
        {"id": latest, "modificacao": "10/07/2024"},
    ]


def test_parse_latest_period_ignores_malformed_rows():
    parsed = parse_latest_period([{"id": "annual"}, *_periods()])
    assert parsed == {
        "official_period_id": "202406",
        "official_reference_month": "2024-06",
        "source_modified_at": "2024-07-10",
    }


def test_probe_reports_current_and_new(tmp_path):
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps({"reference_month": "2024-06"}), encoding="utf-8")
    current = probe_release(diagnostic, fetch_json=lambda url: _periods(), detected_at="now")
    assert current["status"] == "current"
    assert current["requires_full_rebuild"] is False
    assert current["source_url"] == PERIODS_URL

    diagnostic.write_text(json.dumps({"reference_month": "2024-05"}), encoding="utf-8")
    new = probe_release(diagnostic, fetch_json=lambda url: _periods(), detected_at="now")
    assert new["status"] == "new"
    assert new["requires_full_rebuild"] is False


def test_probe_missing_or_malformed_local_state_requires_full_rebuild(tmp_path):
    missing = probe_release(tmp_path / "missing.json", fetch_json=lambda url: _periods())
    assert missing["status"] == "new"
    assert missing["requires_full_rebuild"] is True

    bad = tmp_path / "bad.json"
    bad.write_text("{bad", encoding="utf-8")
    malformed = probe_release(bad, fetch_json=lambda url: _periods())
    assert malformed["requires_full_rebuild"] is True


def test_request_json_retries_malformed_payload_and_fails_closed():
    calls = []
    sleeps = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"not-json"

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        return Response()

    with pytest.raises(ReleaseProbeError):
        _request_json(
            PERIODS_URL,
            attempts=3,
            timeout=1.0,
            opener=opener,
            sleeper=sleeps.append,
        )
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_request_json_accepts_gzip_from_official_api():
    class Response:
        headers = {"Content-Encoding": "gzip"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return gzip.compress(json.dumps(_periods()).encode("utf-8"))

    payload = _request_json(PERIODS_URL, attempts=1, opener=lambda *args, **kwargs: Response())
    assert payload[-1]["id"] == "202406"


def test_next_release_date_uses_reference_month_not_list_order():
    payload = {
        "items": [
            {
                "ano_referencia_inicio": 2024,
                "mes_referencia_inicio": 8,
                "data_divulgacao": "10/09/2024 12:00:00",
            },
            {
                "ano_referencia_inicio": 2024,
                "mes_referencia_inicio": 7,
                "data_divulgacao": "09/08/2024 12:00:00",
            },
        ]
    }
    assert next_release_date("2024-06", fetch_json=lambda url: payload) == "2024-08-09"


def test_release_state_loader_and_runtime_freshness(tmp_path):
    state = build_release_state(
        "2024-06",
        built_at="2024-07-10T12:10:00+00:00",
        next_release="2024-08-09",
    )
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    assert load_release_state(path)["reference_month"] == "2024-06"
    assert freshness_status(state, today=date(2024, 8, 8)) == "current"
    assert freshness_status(state, today=date(2024, 8, 9)) == "due_today"
    assert freshness_status(state, today=date(2024, 8, 10)) == "overdue"
    path.write_text("[]", encoding="utf-8")
    assert load_release_state(path) == {}
