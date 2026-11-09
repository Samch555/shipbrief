"""Polite HTTP client: timeouts, retries with backoff, size cap, robots.txt check.

Standard library only. Never logs request headers (which may carry secrets).
"""
from __future__ import annotations

import gzip
import logging
import threading
import time
import urllib.error
import urllib.request
import urllib.robotparser
from typing import Callable
from urllib.parse import urlsplit

from . import config

log = logging.getLogger(__name__)


class FetchError(Exception):
    pass


class RobotsDisallowed(FetchError):
    pass


_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_robots_lock = threading.Lock()

# Hosts whose content is fetched through an official public API with no robots.txt
# semantics (robots.txt governs crawlers of web pages, not documented JSON APIs).
ROBOTS_EXEMPT_HOSTS = {"hn.algolia.com", "api.anthropic.com"}


def _raw_get(url: str, timeout: float, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={
        "User-Agent": config.USER_AGENT,
        "Accept": "application/atom+xml, application/rss+xml, application/xml, application/json, text/xml;q=0.9, */*;q=0.5",
        "Accept-Encoding": "gzip",
        **(headers or {}),
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (http/https only, checked by caller)
        data = resp.read(config.MAX_RESPONSE_BYTES + 1)
        if len(data) > config.MAX_RESPONSE_BYTES:
            raise FetchError(f"response larger than {config.MAX_RESPONSE_BYTES} bytes")
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            data = gzip.decompress(data)
        return resp.status, data


def robots_allows(url: str, timeout: float = config.HTTP_TIMEOUT_SECONDS) -> bool:
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host in ROBOTS_EXEMPT_HOSTS:
        return True
    base = f"{parts.scheme}://{parts.netloc}"
    with _robots_lock:
        cached = _robots_cache.get(base, "missing")
    if cached == "missing":
        rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        try:
            status, body = _raw_get(base + "/robots.txt", timeout)
            rp.parse(body.decode("utf-8", errors="replace").splitlines())
        except urllib.error.HTTPError as e:
            # 4xx -> no robots.txt -> everything allowed; 5xx -> be conservative? Python's
            # stdlib treats 401/403 as disallow-all. We follow the same convention.
            if e.code in (401, 403):
                rp.disallow_all = True
            else:
                rp.allow_all = True
        except Exception:  # network error: don't block on robots; feed fetch will fail anyway
            rp = None
        with _robots_lock:
            _robots_cache[base] = rp
        cached = rp
    if cached is None:
        return True
    return cached.can_fetch(config.USER_AGENT, url)


def get(url: str, *, timeout: float = config.HTTP_TIMEOUT_SECONDS,
        retries: int = config.HTTP_RETRIES, check_robots: bool = True,
        sleep: Callable[[float], None] = time.sleep) -> bytes:
    """GET a URL with retries. Raises FetchError on final failure."""
    if urlsplit(url).scheme not in ("http", "https"):
        raise FetchError(f"refusing non-http url: {url}")
    if check_robots and not robots_allows(url, timeout):
        raise RobotsDisallowed(f"robots.txt disallows {url}")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            status, data = _raw_get(url, timeout)
            if status >= 400:
                raise FetchError(f"HTTP {status}")
            return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 401, 403, 404, 410, 451):
                break  # permanent; don't hammer
        except Exception as e:  # timeouts, DNS, resets
            last = e
        if attempt < retries:
            sleep(config.HTTP_BACKOFF_SECONDS * (2 ** attempt))
    raise FetchError(f"{type(last).__name__}: {str(last)[:160]}")
