"""Scraper for 明愛 Caritas Hong Kong (caritas.org.hk).

Strategy:
- Job listing is a server-rendered table at /en/job_vacancy/main/3/
  (columns: Post Title | Type of Service | Work Location | Ref. No. |
  Deadline | Details). "Details" links are PDFs; we keep the apply_url
  pointing at the PDF and use the table row as the job record.
- Paginate ?page=N until a page yields no rows.
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

SOURCE = "caritas"
SOURCE_NAME = "明愛"
BASE = "https://www.caritas.org.hk"
LIST_URL = BASE + "/en/job_vacancy/main/3/?order=desc&page={page}"

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


def _cell(raw):
    t = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _parse_rows(html):
    """Yield dicts from the listing table rows."""
    jobs = []
    for m in re.finditer(r"<tr>(.*?)</tr>", html, re.S | re.I):
        row = m.group(1)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S | re.I)
        if len(cells) < 5:
            continue
        title = _cell(cells[0])
        level = classify(title)
        if not level:
            continue
        service = _cell(cells[1])
        location = _cell(cells[2])
        ref = _cell(cells[3])
        deadline = _cell(cells[4])
        pdf = re.search(r'href="([^"]+)"', cells[5] if len(cells) > 5 else "", re.I)
        apply_url = (BASE + pdf.group(1)) if pdf else LIST_URL.format(page=1)
        desc = "Type of Service: " + service
        if deadline:
            desc += "\nDeadline: " + deadline
        desc = desc[:MAX_DESC]
        jobs.append({
            "source": SOURCE,
            "external_id": ref or title[:40],
            "title": title,
            "company": "香港明愛",
            "salary": "",
            "location": location,
            "employment": "",
            "level": level,
            "posted_date": "",
            "description": desc,
            "requirements": "",
            "apply_url": apply_url,
            "logo_url": None,
        })
    return jobs


def scrape():
    """Return job dicts; [] on any failure."""
    try:
        out = []
        seen = set()
        for page in range(1, 6):  # cap pages; site has few listings
            html = _get(LIST_URL.format(page=page))
            if not html:
                break
            rows = _parse_rows(html)
            if not rows:
                break
            new = 0
            for j in rows:
                if j["external_id"] not in seen:
                    seen.add(j["external_id"])
                    out.append(j)
                    new += 1
            if new == 0:
                break
        return out
    except Exception:
        return []
