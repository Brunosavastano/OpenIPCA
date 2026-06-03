"""Shared HTTP session with retries for the public data APIs.

The IBGE/SIDRA API is slow and flaky, especially from outside Brazil (for
example, a GitHub Actions runner). The pipeline makes many sequential calls, so
a single transient connect/read timeout must not kill the whole monthly refresh.
This returns a requests.Session that retries connect/read timeouts and common
transient HTTP statuses with bounded exponential backoff.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

TRANSIENT_STATUSES = (429, 500, 502, 503, 504)


def session_with_retries(
    total: int = 3,
    backoff_factor: float = 1.0,
    backoff_max: float = 20.0,
) -> requests.Session:
    """A requests Session that retries transient failures (timeouts, 5xx, 429).

    The cap and disabled Retry-After handling keep an upstream 429 from sleeping
    the refresh job for an arbitrary server-provided delay.
    """
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        backoff_max=backoff_max,
        status_forcelist=TRANSIENT_STATUSES,
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
        respect_retry_after_header=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
