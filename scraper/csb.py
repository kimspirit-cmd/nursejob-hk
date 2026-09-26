"""Scraper for 公務員事務局政府職位空缺 (csboa2.csb.gov.hk).

Strategy:
- The Government Vacancies Advertising & Enquiry System is a plain
  server-rendered Struts app with no bot protection; plain GET works.
- The default search page (JVE_001_text.action, 全選 tab) lists every open
  vacancy server-side with links to detail pages
  (JVE_003_text.action?jobid=NNNNN).
- Filter titles with the shared nurse keyword classifier, then fetch each
  detail page for department / salary / entry requirements / duties /
  publish date. Detail pages are simple label/value tables.
- Dedupe key: CSB job id (職位編號).
"""
import html as htmlmod
import re
from datetime import date

from . import fetcher as http  # aliased: module renamed from http.py to avoid shadowing stdlib `http` in script mode
from .keywords import classify

SOURCE = "csb"
SOURCE_NAME = "公務員事務局"
SEARCH_URL = ("https://csboa2.csb.gov.hk/csboa/jve/"
              "JVE_001_text.action?languageType=1")
DETAIL_URL = ("https://csboa2.csb.gov.hk/csboa/jve/"
              "JVE_003_text.action?jobid={jobid}&languageType=1")


def _clean(cell):
    t = re.sub(r"<br\s*/?>", "\n", cell, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = htmlmod.unescape(t)
    t = t.replace("\r", "\n")
    t = re.sub(r"[ \t\xa0]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _field(html, label):
    """Extract the value cell that follows a label cell like <td>部門:</td>."""
    m = re.search(
        r"<td[^>]*>\s*" + re.escape(label) + r"\s*:?\s*</td>\s*"
        r"<td[^>]*>(.*?)</td>",
        html, re.S,
    )
    return _clean(m.group(1)) if m else ""


def _posted(raw):
    """08/07/2026 (DD/MM/YYYY) -> 2026-07-08."""
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw.strip())
    if not m:
        return ""
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return ""


def _employment(terms):
    if "非公務員合約" in terms:
        return "非公務員合約"
    if "公務員" in terms:
        return "公務員"
    return ""


def parse_search(html):
    """Return [(jobid, title)] for every vacancy on the search page."""
    found = {}
    for m in re.finditer(
        r"JVE_003_text\.action\?jobid=(\d+)&amp;languageType=1\"[^>]*>([^<]+)</a>",
        html,
    ):
        jobid, title = m.group(1), htmlmod.unescape(m.group(2)).strip()
        if title and not title.isdigit():
            found[jobid] = title
    return list(found.items())


def parse_detail(html, jobid):
    title = _field(html, "職位名稱")
    level = classify(title)
    if not level:
        return None
    department = _field(html, "部門")
    duties = _field(html, "職責")
    closing = _field(html, "截止申請日期(日/月/年)")
    description = duties
    if closing:
        description = (description + "\n\n【截止申請日期：" + closing + "】").strip()
    return {
        "source": SOURCE,
        "external_id": jobid,
        "title": title,
        "company": department,
        "salary": _field(html, "薪酬"),
        "location": "",
        "employment": _employment(_field(html, "聘用條款")),
        "level": level,
        "posted_date": _posted(_field(html, "發布日期")),
        "description": description,
        "requirements": _field(html, "入職條件"),
        "apply_url": DETAIL_URL.format(jobid=jobid),
        "logo_url": None,
    }


def scrape():
    html = http.fetch(SEARCH_URL)
    if not html:
        raise RuntimeError("CSB search page fetch failed")
    jobs = []
    for jobid, title in parse_search(html):
        if not classify(title):
            continue
        detail = http.fetch(DETAIL_URL.format(jobid=jobid))
        if not detail:
            continue
        job = parse_detail(detail, jobid)
        if job:
            jobs.append(job)
    return jobs
