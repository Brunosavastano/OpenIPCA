"""The shared HTTP session must actually retry transient failures.

The monthly refresh hits the flaky IBGE/SIDRA API many times; a session without
retries lets one transient timeout kill the whole run (observed live on a GitHub
runner). These pin that the retry policy is mounted for both schemes.
"""

from urllib3.util.retry import Retry

from ipca_dashboard._http import session_with_retries


def test_retry_adapter_mounted_for_both_schemes():
    session = session_with_retries(total=4, backoff_factor=2.0)
    for url in ("https://apisidra.ibge.gov.br/x", "http://example/x"):
        retry = session.get_adapter(url).max_retries
        assert isinstance(retry, Retry)
        assert retry.total == 4
        assert retry.connect == 4 and retry.read == 4
        assert retry.backoff_factor == 2.0


def test_retry_covers_transient_statuses_and_timeouts():
    retry = session_with_retries().get_adapter("https://x/").max_retries
    assert retry.total >= 3  # rides out a flaky upstream
    for status in (429, 500, 502, 503, 504):
        assert status in retry.status_forcelist


def test_retry_does_not_retry_non_transient_statuses_or_non_get_methods():
    retry = session_with_retries().get_adapter("https://x/").max_retries
    for status in (400, 401, 403, 404, 422):
        assert not retry.is_retry("GET", status)
    assert not retry.is_retry("POST", 500)


def test_retry_backoff_is_explicitly_bounded():
    retry = session_with_retries().get_adapter("https://x/").max_retries
    assert retry.backoff_max <= 20.0
    assert retry.respect_retry_after_header is False
