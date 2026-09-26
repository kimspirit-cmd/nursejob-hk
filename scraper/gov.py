"""Scraper for Labour Department Interactive Employment Service (www1.jobs.gov.hk).

Strategy:
- Crawl quickview listings for Hospital industry (inds/2) + Care Services (careservices),
  paginated 20/page.
- Keyword-filter titles -> fetch jobCard detail pages for nurse hits.
- Dedupe key: Job Order Number (e.g. 32-26-0013053).
"""
import html as htmlmod
import re
from datetime import datetime

from . import fetcher as http  # aliased: module renamed from http.py to avoid shadowing stdlib `http` in script mode
from .keywords import classify

BASE = "https://www1.jobs.gov.hk"
CATEGORIES = ["inds/2", "careservices"]
SOURCE = "gov"
SOURCE_NAME = "勞工處互動就業服務"

ROW_RE = re.compile(
    r'<div class="row item p-1 no-gutters" data-roworder="\d+" '
    r'data-prev="(?P<order>[^"]+)" data-jobcard="(?P<jobcard>[^"]+)">(.*?)'
    r'<div class="col-auto pr-1 text-center">\s*<span>\d+\.</span>',
    re.S,
)


def _strip(html: str) -> str:
    t = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", "|", t)
    t = htmlmod.unescape(t)
    t = re.sub(r"\|+", "|", t)
    return t


def _field(text: str, label: str, stop_labels: tuple = ()) -> str:
    """Extract 'label value' from pipe-separated stripped text."""
    m = re.search(re.escape(label) + r"\s*\|\s*([^|]{1,600})", text)
    if not m:
        return ""
    val = m.group(1).strip()
    return val


def parse_list(html: str) -> list:
    # live pages contain literal backslash-r-n sequences; normalize them
    html = html.replace("\\r\\n", "\n").replace("\\r", "\n").replace("\\n", "\n")
    jobs = []
    row_iter = list(re.finditer(
        r'<div class="row item p-1 no-gutters" data-roworder="\d+" '
        r'data-prev="(?P<order>[^"]*)" data-jobcard="(?P<jobcard>[^"]+)">',
        html,
    ))
    for idx, m in enumerate(row_iter):
        order = m.group("order").strip()
        jobcard = htmlmod.unescape(m.group("jobcard"))
        end = row_iter[idx + 1].start() if idx + 1 < len(row_iter) else m.end() + 4000
        block = html[m.end():end]
        if not order:
            om = re.search(r'data-ordno="([^"]+)"', block)
            order = om.group(1).strip() if om else ""
        tm = re.search(
            r'<div class="d-flex justify-content-between pb-2">\s*<div>([^<]+)</div>',
            block,
        )
        title = htmlmod.unescape(tm.group(1)).strip() if tm else ""
        sm = re.search(r'icon_salary[^>]*>([^<]+)<', block)
        lm = re.search(r'icon_address[^>]*>([^<]+)<', block)
        salary = htmlmod.unescape(sm.group(1)).strip() if sm else ""
        location = htmlmod.unescape(lm.group(1)).strip() if lm else ""
        if not order:
            continue
        jobs.append({
            "order": order,
            "title": title,
            "salary": salary,
            "location": location,
            "detail_url": BASE + jobcard,
        })
    return jobs


def parse_detail(html: str) -> dict:
    if not html:
        return {"posted_date": "", "company": "", "description": "", "requirements": ""}
    # live pages contain literal backslash-n sequences; normalize before regex
    html = html.replace("\\r\\n", "\n").replace("\\r", "\n").replace("\\n", "\n")

    def by_id(span_id: str) -> str:
        m = re.search(
            r'<span id="%s"[^>]*>(.*?)</span>' % re.escape(span_id), html, re.S
        )
        return _strip(m.group(1)) if m else ""

    posted = ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", by_id("postedDt"))
    if m:
        posted = f"{m.group(3)}-{m.group(2).zfill(2)}-{m.group(1).zfill(2)}"
    return {
        "posted_date": posted,
        "company": by_id("empName"),
        "description": by_id("jobRemark"),
        "requirements": by_id("eduRemark"),
    }


def scrape() -> list:
    """Keyword search (POST) per language, then paginate via session GET."""
    results = []
    seen_orders = set()
    for lang, keywords in (("en", ["nurse", "RN", "EN"]), ("tc", ["護士"])):
        search_url = f"{BASE}/0/{lang}/jobseeker/jobsearch/search/"
        form_html = http.fetch(search_url)
        if not form_html:
            continue
        tok = re.search(
            r'name="__RequestVerificationToken" type="hidden" value="([^"]+)"',
            form_html,
        )
        token = tok.group(1) if tok else ""
        for kw in keywords:
            data = {
                "__RequestVerificationToken": token,
                "criteria.searchField": kw,
                "criteria.searchByOption": "1",  # 1 = Keyword mode
                "criteria.sortBy": "post_dt_desc",
            }
            html = http.fetch_post(search_url, data)
            if not html:
                continue
            m = re.search(r"of <strong>(\d+)</strong>", html)
            total = int(m.group(1)) if m else 20
            pages = min((total + 19) // 20, 30)
            for page in range(1, pages + 1):
                if page > 1:
                    html = http.fetch(
                        f"{BASE}/0/{lang}/jobseeker/jobsearch/quickview/"
                        f"?direct=False&page={page}"
                    )
                    if not html:
                        break
                rows = parse_list(html)
                if not rows:
                    break
                for r in rows:
                    if r["order"] in seen_orders:
                        continue
                    seen_orders.add(r["order"])
                    level = classify(r["title"])
                    if not level:
                        continue
                    detail_html = http.fetch(r["detail_url"])
                    detail = parse_detail(detail_html) if detail_html else {}
                    results.append({
                        "source": SOURCE,
                        "external_id": r["order"],
                        "title": r["title"],
                        "company": detail.get("company", ""),
                        "salary": r["salary"],
                        "location": r["location"],
                        "employment": "",
                        "level": level,
                        "posted_date": detail.get("posted_date", ""),
                        "description": detail.get("description", ""),
                        "requirements": detail.get("requirements", ""),
                        "apply_url": r["detail_url"],
                        "logo_url": "",
                    })
    return results
