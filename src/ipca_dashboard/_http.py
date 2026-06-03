"""Shared HTTP session with retries for the public data APIs.

The IBGE/SIDRA API is slow and flaky — especially from outside Brazil (e.g. a
GitHub Actions runner) — and the pipeline makes many sequential calls, so a
single transient connect/read timeout must not kill the whole monthly refresh.
This returns a requests.Session that retries connect/read timeouts and the
common transient HTTP statuses with exponential backoff.
"""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def session_with_retries(total: int = 5, backoff_factor: float = 1.5) -> requests.Session:
    """A requests Session that retries transient failures (timeouts, 5xx, 429).

    backoff_factor=1.5 with total=5 spaces retries by ~0, 3, 6, 12, 24s — enough
    to ride out a flaky upstream without hanging forever.
    """
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
