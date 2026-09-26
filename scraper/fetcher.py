"""Polite HTTP fetcher shared by all scrapers.

- Identifies itself with a descriptive User-Agent
- Enforces a minimum delay between requests per domain
- Retries transient failures a couple of times
- Shares one session so cookies persist (needed for jobs.gov.hk search flow)
"""
import time
import urllib.parse

import requests

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "NurseJobsHK/1.0 (+daily nurse-vacancy aggregator)"
)

MIN_DELAY = 1.0  # seconds between requests to the same domain
TIMEOUT = 40

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8"})

_last_fetch: dict = {}


def _polite_wait(url: str) -> None:
    domain = urllib.parse.urlparse(url).netloc
    now = time.time()
    last = _last_fetch.get(domain, 0)
    wait = MIN_DELAY - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_fetch[domain] = time.time()


def fetch(url: str, retries: int = 2) -> str | None:
    """GET url and return text, or None on persistent failure."""
    for attempt in range(retries + 1):
        try:
            _polite_wait(url)
            r = _session.get(url, timeout=TIMEOUT)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            if r.status_code in (404, 410):
                return None
            # 429 / 5xx -> back off and retry
            time.sleep(3 * (attempt + 1))
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
    return None


def fetch_post(url: str, data: dict, retries: int = 2) -> str | None:
    """POST url with form data using the shared session (keeps cookies)."""
    for attempt in range(retries + 1):
        try:
            _polite_wait(url)
            r = _session.post(url, data=data, timeout=TIMEOUT)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            time.sleep(3 * (attempt + 1))
        except requests.RequestException:
            time.sleep(3 * (attempt + 1))
    return None
