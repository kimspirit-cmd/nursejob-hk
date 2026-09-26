"""Scraper for CTgoodjobs (www.ctgoodjobs.hk).

Strategy:
- The jobs.* subdomain and the JSON search API are bot-walled (dropped
  connections), and job detail pages don't return content to scrapers, so
  this source is listing-only.
- The legacy www .asp search listing IS plain server-rendered HTML and
  fetches fine: crawl the "NGO / Social Service - Nurse" category
  (job_area=520), all pages. Each row gives title, company, salary and
  posted date; apply_url points at the site's own detail link, which opens
  fine in a real browser.
- Dedupe key: ctgoodjobs job id (m_jobid).
"""
import html as htmlmod
import re
from datetime import date

from . import fetcher as http  # aliased: module renamed from http.py to avoid shadowing stdlib `http` in script mode
from .keywords import classify

SOURCE = "ctgoodjobs"
SOURCE_NAME = "CTgoodjobs"
LIST_URL = ("https://www.ctgoodjobs.hk/english/search/summary_ngo.asp"
            "?joblistmode=columnlist&job_area=520&search=Y&fulltext=Y"
            "&include_no_salary=Y&page={page}")


def _clean(cell: str) -> str:
    t = re.sub(r"<[^>]+>", " ", cell)
    t = htmlmod.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _posted(raw: str) -> str:
    """26/09/26 -> 2026-09-26."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", raw.strip())
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def _salary(raw: str) -> str:
    s = _clean(raw)
    if not s or s == "-":
        return ""
    return re.sub(r"\s+", " ", s)


def parse_list(html: str) -> list:
    jobs = []
    rows = re.findall(r"<tr[^>]*id='entry\d+'[^>]*>(.*?)</tr>", html, re.S)
    for r in rows:
        m = re.search(r"m_jobid=(\d+)", r)
        if not m:
            continue
        jid = m.group(1)
        cells = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        if len(cells) < 6:
            continue
        tm = re.search(r"class='joblisting_url01[^']*'>(.*?)</a>", cells[1], re.S)
        title = _clean(tm.group(1)) if tm else ""
        if not title:
            continue
        hm = re.search(r'href="([^"]*jobsdetails\.asp[^"]*)"', cells[1])
        href = hm.group(1).replace("&amp;", "&") if hm else ""
        if href.startswith("../"):
            href = "https://www.ctgoodjobs.hk/english/" + href[3:]
        company = _clean(cells[2])
        level = classify(title)
        if not level:
            continue
        jobs.append({
            "source": SOURCE,
            "external_id": jid,
            "title": title,
            "company": company,
            "salary": _salary(cells[4]),
            "location": "",
            "employment": "",
            "level": level,
            "posted_date": _posted(_clean(cells[5])),
            "description": "",
            "requirements": "",
            "apply_url": href,
            "logo_url": "",
        })
    return jobs


def total_pages(html: str) -> int:
    m = re.search(r'id="page_total_count_global"[^>]*value="(\d+)"', html)
    try:
        return max(1, int(m.group(1))) if m else 1
    except ValueError:
        return 1


def scrape() -> list:
    first = http.fetch(LIST_URL.format(page=1))
    if not first:
        return []
    pages = total_pages(first)
    results = parse_list(first)
    seen = {j["external_id"] for j in results}
    for p in range(2, pages + 1):
        html = http.fetch(LIST_URL.format(page=p))
        if not html:
            continue
        for j in parse_list(html):
            if j["external_id"] not in seen:
                seen.add(j["external_id"])
                results.append(j)
    return results
