"""Scraper for 東華三院 Tung Wah Group of Hospitals (tungwah.org.hk).

Strategy:
- Vacancy detail pages live at /en/vacancy/{slug}/ but the site exposes no
  stable listing/archive page, so we probe a small set of candidate listing
  URLs and parse any vacancy links found. If nothing is reachable, return [].
- Filter titles with the shared nurse keyword classifier.

Defensive: any failure -> return [].
- timeout=5, headers={'User-Agent': 'Mozilla/5.0'}
- logo_url = None, never store base64
- description truncated at 500 chars
"""
import html as htmlmod
import re

import requests

from .keywords import classify

SOURCE = "tungwah"
SOURCE_NAME = "東華三院"
BASE = "https://www.tungwah.org.hk"

CANDIDATE_LISTINGS = [
    BASE + "/en/vacancy/",
    BASE + "/vacancy/",
    BASE + "/tc/careers/career-opportunities/",
    BASE + "/en/careers/career-opportunities/",
]

TIMEOUT = 5
MAX_DESC = 500

_HEADERS = {"User-Agent": "Mozilla/5.0"}


def _get(url):
    try:
        r = requests.get(url, headers=_HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
    except requests.RequestException:
        pass
    return None


def _text(raw):
    t = re.sub(r"<br\s*/?>", "\n", raw, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _parse_detail(html, url):
    m = re.search(r"<title>([^<]+)</title>", html, re.I)
    title = _text(m.group(1)).split("|")[0].strip() if m else ""
    level = classify(title)
    if not level:
        return None
    # Job content is usually in the main article body
    body = re.search(
        r'<div[^>]*class="[^"]*(?:entry-content|post-content|content)[^"]*"[^>]*>(.*?)</div>',
        html, re.S | re.I,
    )
    desc = _text(body.group(1))[:MAX_DESC] if body else ""
    # strip any accidental data: URIs
    desc = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "", desc, flags=re.I)
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    return {
        "source": SOURCE,
        "external_id": slug,
        "title": title,
        "company": "東華三院",
        "salary": "",
        "location": "",
        "employment": "",
        "level": level,
        "posted_date": "",
        "description": desc,
        "requirements": "",
        "apply_url": url,
        "logo_url": None,
    }


def scrape():
    """Return job dicts; [] on any failure."""
    try:
        links = {}
        for listing in CANDIDATE_LISTINGS:
            html = _get(listing)
            if not html or "沒有符合條件的頁面" in html or "Not Found" in html[:2000]:
                continue
            for m in re.finditer(r'href="((?:https://www\.tungwah\.org\.hk)?/(?:en/)?vacancy/[^"]+/)"', html, re.I):
                u = m.group(1)
                if u.startswith("/"):
                    u = BASE + u
                links[u] = True
            if links:
                break
        out = []
        for url in list(links)[:30]:
            html = _get(url)
            if not html:
                continue
            job = _parse_detail(html, url)
            if job:
                out.append(job)
        return out
    except Exception:
        return []
