"""Scraper for 明報 JUMP (jump.mingpao.com).

Strategy:
- Crawl the Health Care category listing (JobAreaID[]=13-0), 20/page, SSR.
- Keyword-filter titles -> fetch detail pages for nurse hits.
- Dedupe key: job ID from the detail URL (e.g. HS26084924).
"""
import html as htmlmod
import re
from datetime import datetime

from . import fetcher as http, clean_text  # fetcher.py renamed from http.py to avoid shadowing stdlib `http` in script mode
from .keywords import classify

SOURCE = "jump"
SOURCE_NAME = "明報 JUMP"

LIST_URL = "https://jump.mingpao.com/job/search/Jobs/2?JobAreaID%5B%5D=13-0"

ROW_RE = re.compile(
    r'href="(?P<url>[^"]+/job/detail/Jobs/2/(?P<jobid>[^/"]+)/[^"]*)">'
    r'<i class="jump_ui ui_star"></i>(?P<title>[^<]+)</a>.*?'
    r'CustNo=[^"]*">(?P<company>[^<]+)</a>.*?'
    r'<div class="thum13percent">(?P<date>[^<]+)</div>',
    re.S,
)

MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
          "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}


def parse_short_date(s: str) -> str:
    # "25 Sep 26" -> 2026-09-25 ; "25 Sep 2026" -> 2026-09-25
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})", s or "")
    if not m:
        return ""
    year = int(m.group(3))
    if year < 100:
        year += 2000
    return f"{year}-{MONTHS.get(m.group(2).title(), 1):02d}-{int(m.group(1)):02d}"


def _strip(html: str) -> str:
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "|", t)
    t = htmlmod.unescape(t)
    return re.sub(r"\|+", "|", t)


def _label(text: str, label: str) -> str:
    m = re.search(re.escape(label) + r":\s*([^|]{1,300})", text)
    return m.group(1).strip(" |") if m else ""


def parse_detail(html: str) -> dict:
    text = _strip(html)
    # Descriptions ... Enquiries ...
    desc = ""
    m = re.search(r"Descriptions\s*\|(.*?)\|\s*Enquiries", text, re.S)
    if m:
        desc = clean_text(re.sub(r"\|+", " ", m.group(1)))
    enq = ""
    m2 = re.search(r"Enquiries\s*\|(.*)", text, re.S)
    if m2:
        enq = clean_text(re.sub(r"\|+", " ", m2.group(1)))[:1200].strip()
    company = ""
    m3 = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.S)
    if m3:
        company = htmlmod.unescape(re.sub(r"<[^>]+>", "", m3.group(1))).strip()
    return {
        "posted_date": parse_short_date(_label(text, "Post Date")),
        "functions": _label(text, "Functions"),
        "employment": _label(text, "Types"),
        "education": _label(text, "Education"),
        "salary": _label(text, "Salary"),
        "location": _label(text, "Location"),
        "company": company,
        "description": desc,
        "requirements": enq,
    }


def total_pages(html: str) -> int:
    m = re.search(r"Total\s+(\d+)\s+Page", html)
    return int(m.group(1)) if m else 1


def scrape() -> list:
    results = []
    seen_ids = set()
    first = http.fetch(LIST_URL)
    if not first:
        return results
    pages = min(total_pages(first), 40)
    for page in range(1, pages + 1):
        url = LIST_URL if page == 1 else f"{LIST_URL}&Page={page}"
        html = http.fetch(url) if page > 1 else first
        if not html:
            continue
        for m in ROW_RE.finditer(html):
            jobid = m.group("jobid")
            if jobid in seen_ids:
                continue
            seen_ids.add(jobid)
            title = htmlmod.unescape(m.group("title")).strip()
            level = classify(title)
            if not level:
                continue
            detail_html = http.fetch(m.group("url"))
            d = parse_detail(detail_html) if detail_html else {}
            results.append({
                "source": SOURCE,
                "external_id": jobid,
                "title": title,
                "company": d.get("company") or htmlmod.unescape(m.group("company")).strip(),
                "salary": d.get("salary", ""),
                "location": d.get("location", ""),
                "employment": d.get("employment", ""),
                "level": level,
                "posted_date": d.get("posted_date") or parse_short_date(m.group("date")),
                "description": d.get("description", ""),
                "requirements": d.get("requirements", ""),
                "apply_url": m.group("url"),
                "logo_url": "",
            })
    return results
