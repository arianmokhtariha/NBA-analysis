"""Shared HTTP layer for every basketball-reference scraper.

Every other module in this package fetches pages through
:func:`fetch_page` rather than calling `requests` directly. Keeping
the network code in one place is what makes the "be polite to
basketball-reference.com" behaviour (retries, backing off on 429,
throttling between requests) apply everywhere automatically instead
of being copy-pasted per scraper.

Building a session (:func:`build_session`) never touches the network
by itself - a scraper decides when to fetch by calling
:func:`fetch_page` explicitly. This is the fix for the old
`BasketballScraper.__init__`, which used to fire two live HTTP
requests just from being constructed.
"""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://www.basketball-reference.com/"

# Rotated per request so repeated hits to the same host don't all look
# identical. Ordinary desktop/mobile browser strings, nothing exotic.
USER_AGENTS: list[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/116.0.5845.96 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 "
    "Firefox/130.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.6 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6; rv:130.0) Gecko/20100101 "
    "Firefox/130.0",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 "
    "Safari/604.1",
]

# basketball-reference returns a plain 403 to bare "python-requests"
# style headers; this set of browser-navigation headers is what gets a
# normal 200 (verified live while writing this module).
DEFAULT_HEADERS: dict[str, str] = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://google.com/",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
}


def build_session(extra_headers: dict[str, str] | None = None) -> requests.Session:
    """Create a `requests.Session` pre-loaded with browser-like headers.

    This performs no network I/O - it just prepares a session object.
    `extra_headers` can override or add to the defaults.
    """
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if extra_headers:
        session.headers.update(extra_headers)
    return session


def fetch_page(
    session: requests.Session,
    url: str,
    *,
    max_retries: int = 5,
    delay: float = 3.0,
) -> str | None:
    """Fetch `url` and return its HTML, or None if every attempt failed.

    Behaviour, in order of priority:

    - Rotates the `User-Agent` header on every attempt.
    - On HTTP 429 (rate limited), waits `delay` seconds (plus jitter)
      and retries instead of giving up immediately.
    - On any other network error, also retries with the same backoff.
    - On success, sleeps `delay` seconds before returning. This is
      what throttles a caller looping over many URLs - as long as
      every fetch goes through this function, consecutive requests to
      basketball-reference.com are always at least `delay` seconds
      apart.
    """
    for attempt in range(1, max_retries + 1):
        session.headers["User-Agent"] = random.choice(USER_AGENTS)
        try:
            response = session.get(url, timeout=30)
            if response.status_code == 429:
                wait = delay + random.uniform(0, 2)
                logger.warning(
                    "429 Too Many Requests on %s; waiting %.1fs "
                    "(attempt %d/%d)",
                    url,
                    wait,
                    attempt,
                    max_retries,
                )
                time.sleep(wait)
                continue
            response.raise_for_status()
            time.sleep(delay)
            return response.text
        except requests.RequestException as exc:
            wait = delay + random.uniform(0, 2)
            logger.warning(
                "Request to %s failed (%s); retrying in %.1fs "
                "(attempt %d/%d)",
                url,
                exc,
                wait,
                attempt,
                max_retries,
            )
            time.sleep(wait)

    logger.error("Failed to fetch %s after %d attempts.", url, max_retries)
    return None


def normalize_url(url: str) -> str:
    """Strip a URL's fragment (the '#...' part), leaving a clean link."""
    return urlparse(url)._replace(fragment="").geturl()
