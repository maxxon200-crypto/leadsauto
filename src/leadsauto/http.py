"""A polite, resilient HTTP client for scraping.

Design goals:

* **Be a good citizen** – honour ``robots.txt`` and rate-limit requests per
  host so we never hammer a directory site.
* **Be resilient** – retry transient failures with exponential backoff.
* **Be testable** – all network behaviour lives behind :class:`HttpClient`, so
  tests can inject a fake client instead of touching the network.
"""

from __future__ import annotations

import logging
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "leadsauto/0.1 (+https://github.com/maxxon200-crypto/leadsauto; "
    "polite B2B contact discovery)"
)


class RobotsDisallowed(Exception):
    """Raised when ``robots.txt`` forbids fetching a URL."""


@dataclass
class HttpClient:
    """Rate-limited HTTP client with robots.txt awareness and retries."""

    user_agent: str = DEFAULT_USER_AGENT
    min_delay: float = 1.0  # minimum seconds between requests to the same host
    timeout: float = 20.0
    respect_robots: bool = True
    max_retries: int = 3

    _session: requests.Session = field(default=None, repr=False)  # type: ignore[assignment]
    _last_request: dict = field(default_factory=dict, repr=False)
    _robots: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        session = requests.Session()
        retry = Retry(
            total=self.max_retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update({"User-Agent": self.user_agent})
        self._session = session

    # -- rate limiting ------------------------------------------------------
    def _throttle(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            elapsed = time.monotonic() - last
            wait = self.min_delay - elapsed
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    # -- robots.txt ---------------------------------------------------------
    def _robots_for(self, url: str) -> Optional[urllib.robotparser.RobotFileParser]:
        parsed = urlparse(url)
        host = parsed.netloc
        if host in self._robots:
            return self._robots[host]
        robots_url = f"{parsed.scheme}://{host}/robots.txt"
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = self._session.get(robots_url, timeout=self.timeout)
            if resp.status_code >= 400:
                rp = None  # no robots.txt -> allow by convention
            else:
                rp.parse(resp.text.splitlines())
        except requests.RequestException:
            rp = None
        self._robots[host] = rp
        return rp

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self._robots_for(url)
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    # -- fetching -----------------------------------------------------------
    def get(self, url: str) -> requests.Response:
        """Fetch ``url`` respecting robots.txt and per-host rate limiting.

        Raises :class:`RobotsDisallowed` if fetching is not permitted.
        """
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        host = urlparse(url).netloc
        self._throttle(host)
        log.debug("GET %s", url)
        resp = self._session.get(url, timeout=self.timeout)
        resp.raise_for_status()
        return resp

    def get_text(self, url: str) -> str:
        return self.get(url).text

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
