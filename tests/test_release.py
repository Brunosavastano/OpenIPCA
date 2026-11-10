import gzip
import importlib.util
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from ipca_dashboard.release import (
    CALENDAR_URL,
    PERIODS_URL,
    SIDRA_LATEST_URL,
    ReleaseProbeError,
    _request_json,
    build_release_state,
    fetch_official_period,
    freshness_status,
    load_calendar_snapshot,
    load_release_state,
    next_release_date,
    outage_is_actionable,
    parse_latest_period,
    parse_sidra_latest_period,
    probe_release,
    release_deadline,
)

ROOT = Path(__file__).resolve().parents[1]


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


def _sidra(period: str = "202406", value: str = "0.21") -> list[dict]:
    header = {"D2C": "Variável (Código)", "D3C": "Mês (Código)", "D4C": "Geral", "V": "Valor"}
    return [header, {"D2C": "63", "D3C": period, "D4C": "7169", "V": value}]


def _sources(responses: dict[str, object]):
    """fetch_json fake keyed by URL; an exception stands for an unreachable source."""
    calls: list[str] = []

    def fetch(url: str) -> object:
        calls.append(url)
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        return response

    fetch.calls = calls
    return fetch


def _blocked(url: str) -> object:
    raise ReleaseProbeError(f"Could not read trusted JSON from {url} (TimeoutError())")


def test_probe_asks_sidra_first_and_never_waits_on_the_blocked_host(tmp_path):
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps({"reference_month": "2024-05"}), encoding="utf-8")
    fetch = _sources({SIDRA_LATEST_URL: _sidra("202406")})
    result = probe_release(diagnostic, fetch_json=fetch, detected_at="now")
    assert result["status"] == "new"
    assert result["official_reference_month"] == "2024-06"
    assert result["source_url"] == SIDRA_LATEST_URL
    assert result["source_modified_at"] == ""
    assert fetch.calls == [SIDRA_LATEST_URL]


def test_probe_falls_back_to_the_periods_api_when_sidra_fails():
    fetch = _sources({SIDRA_LATEST_URL: ReleaseProbeError("cdn down"), PERIODS_URL: _periods()})
    assert fetch_official_period(fetch) == {
        "official_period_id": "202406",
        "official_reference_month": "2024-06",
        "source_modified_at": "2024-07-10",
        "source_url": PERIODS_URL,
    }
    assert fetch.calls == [SIDRA_LATEST_URL, PERIODS_URL]


def test_probe_reports_every_failed_source():
    fetch = _sources(
        {
            SIDRA_LATEST_URL: ReleaseProbeError("sidra timed out"),
            PERIODS_URL: ReleaseProbeError("periods timed out"),
        }
    )
    with pytest.raises(ReleaseProbeError, match="sidra timed out.*periods timed out"):
        fetch_official_period(fetch)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"D3C": "202406"},
        _sidra()[:1],  # header only
        _sidra(value="..."),  # month listed without a published value
        [_sidra()[0], {"D2C": "2265", "D3C": "202406", "D4C": "7169", "V": "4.23"}],
        [_sidra()[0], {"D2C": "63", "D3C": "2024", "D4C": "7169", "V": "0.21"}],
    ],
)
def test_sidra_parser_never_reports_an_unpublished_month(payload):
    with pytest.raises(ReleaseProbeError):
        parse_sidra_latest_period(payload)


def test_request_json_error_names_the_underlying_failure():
    def opener(request, timeout):
        raise TimeoutError("timed out")

    with pytest.raises(ReleaseProbeError, match="TimeoutError"):
        _request_json(PERIODS_URL, attempts=1, opener=opener)


def test_outage_only_needs_someone_once_the_next_release_is_late():
    state = {"reference_month": "2026-09", "next_release_date": "2026-11-12"}
    assert release_deadline(state, "2026-09") == date(2026, 11, 12)
    assert not outage_is_actionable(state, "2026-09", today=date(2026, 11, 9))
    assert not outage_is_actionable(state, "2026-09", today=date(2026, 11, 14))
    assert outage_is_actionable(state, "2026-09", today=date(2026, 11, 15))


def test_outage_without_a_calendar_date_waits_for_the_end_of_the_usual_window():
    stale_state = {"reference_month": "2026-08", "next_release_date": "2026-10-09"}
    for state in ({}, stale_state):
        assert release_deadline(state, "2026-12") == date(2027, 2, 17)
        assert not outage_is_actionable(state, "2026-12", today=date(2027, 2, 19))
        assert outage_is_actionable(state, "2026-12", today=date(2027, 2, 20))
    assert outage_is_actionable({}, "", today=date(2026, 11, 9))


def test_next_release_date_falls_back_to_the_committed_calendar(tmp_path):
    def calendar(release: str) -> dict:
        item = {"ano_referencia_inicio": 2026, "mes_referencia_inicio": 10}
        return {"items": [{**item, "data_divulgacao": f"{release} 12:00:00"}]}

    snapshot = tmp_path / "calendar.json"
    snapshot.write_text(json.dumps(calendar("12/11/2026")), encoding="utf-8")
    assert next_release_date("2026-09", fetch_json=_blocked, snapshot_path=snapshot) == (
        "2026-11-12"
    )
    live = calendar("13/11/2026")
    assert (
        next_release_date("2026-09", fetch_json=lambda url: live, snapshot_path=snapshot)
        == "2026-11-13"
    )
    missing = tmp_path / "missing.json"
    assert next_release_date("2026-09", fetch_json=_blocked, snapshot_path=missing) == ""


def test_committed_calendar_snapshot_keeps_the_official_format():
    snapshot = load_calendar_snapshot()
    assert snapshot["source_url"] == CALENDAR_URL
    first, second = snapshot["items"][:2]
    month = f"{first['ano_referencia_inicio']:04d}-{first['mes_referencia_inicio']:02d}"
    expected = datetime.strptime(second["data_divulgacao"], "%d/%m/%Y %H:%M:%S").date()
    assert next_release_date(month, fetch_json=_blocked) == expected.isoformat()


def _probe_script():
    spec = importlib.util.spec_from_file_location(
        "probe_ipca_release_under_test", ROOT / "scripts" / "probe_ipca_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_script_warns_while_data_is_current_and_fails_once_late(
    tmp_path, monkeypatch, capsys
):
    script = _probe_script()

    def unreachable(path):
        raise ReleaseProbeError("No official IBGE source answered")

    monkeypatch.setattr(script, "probe_release", unreachable)
    outputs = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps({"reference_month": "2026-09"}), encoding="utf-8")
    state = tmp_path / "release_state.json"
    args = ["--json", "--diagnostic", str(diagnostic), "--release-state", str(state)]

    state.write_text(json.dumps(build_release_state("2026-09", next_release="2999-01-01")))
    assert script.main(args) == 0
    printed = capsys.readouterr().out.strip().splitlines()
    assert printed[0].startswith("::warning title=IBGE unreachable::")
    result = json.loads(printed[-1])
    assert result["status"] == "unavailable"
    assert result["next_release_due"] == "2999-01-01"
    written = outputs.read_text(encoding="utf-8")
    assert "status=unavailable\n" in written and "official_month=\n" in written

    state.write_text(json.dumps(build_release_state("2026-09", next_release="2000-01-01")))
    assert script.main(args) == 2
    assert "release probe failed" in capsys.readouterr().err
