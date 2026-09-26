"""Scraper for 保良局職位空缺 (www.poleungkuk.org.hk).

Strategy:
- The career list page (/career) is plain server-rendered HTML with no bot
  protection; plain GET works. Every vacancy links to a detail page
  (/career/YYYY-MM-DD/CODE) that is also server-rendered.
- Pre-filter list link text with the shared nurse keyword classifier, then
  fetch each matching detail page for title / ref no / district / service
  type / deadline / requirements / duties. Detail pages use <dl> label/value
  pairs plus a .ckec rich-text block with 入職要求 / 工作職責 / 其他 sections.
- Dedupe key: the CODE segment of the detail URL (e.g. RN-MKMCFSD1).
- No posted date is published; posted_date stays empty.
"""
import html as htmlmod
import re
from datetime import date

from . import fetcher as http  # aliased: module renamed from http.py to avoid shadowing stdlib `http` in script mode
from .keywords import classify

SOURCE = "plk"
SOURCE_NAME = "保良局"
LIST_URL = "https://www.poleungkuk.org.hk/career"
DETAIL_URL = "https://www.poleungkuk.org.hk{path}"


def _clean(t):
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"<li[^>]*>", "\n- ", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"<[^>]*$", "", t)  # 保良局詳情頁尾有寫爛咗嘅 "<hr"（無閉合）
    t = htmlmod.unescape(t)
    t = t.replace("\xa0", " ").replace("\r", "\n")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def _deadline(raw):
    """2026年10月02日 -> 2026-10-02."""
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", raw.strip())
    if not m:
        return ""
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return ""


def parse_list(html):
    """Return [(path, link_text)] for every vacancy link on the list page."""
    found = {}
    for m in re.finditer(
        r'href="(/career/\d{4}-\d{2}-\d{2}/[^"]+)"[^>]*>(.*?)</a>', html, re.S
    ):
        path, txt = m.group(1), _clean(m.group(2))
        if path not in found:
            found[path] = txt
    return list(found.items())


def _ckec(html):
    """Return the inner HTML of <div class="ckec">…</div>, bounded correctly."""
    i = html.find('<div class="ckec">')
    if i < 0:
        return ""
    j = html.find(">", i) + 1
    depth, k = 1, j
    while depth > 0:
        m = re.search(r"<(/?)div\b", html[k:])
        if not m:
            return html[j:]
        depth += -1 if m.group(1) else 1
        k += m.end()
    return html[j:k - len("</div>")]


def _sections(ckec_html):
    """Split the .ckec block into {heading: text} by its <h2> headings."""
    secs, cur, buf = {}, None, []
    for m in re.finditer(
        r"<h2[^>]*>(.*?)</h2>|(?P<body>.)", ckec_html, re.S
    ):
        if m.group(1) is not None:
            if cur is not None:
                secs[cur] = _clean("".join(buf))
            cur = _clean(m.group(1))
            buf = []
        else:
            if cur is not None:
                buf.append(m.group("body"))
    if cur is not None:
        secs[cur] = _clean("".join(buf))
    return secs


def parse_detail(html, path):
    m = re.search(r'<div class="container"><h2[^>]*>(.*?)</h2>', html, re.S)
    title = _clean(m.group(1)) if m else ""
    level = classify(title)
    if not level:
        return None
    fields = {}
    for k, v in re.findall(
        r'<dt class="career-detail__dt">(.*?)</dt>\s*'
        r'<dd class="career-detail__dd">(.*?)</dd>',
        html, re.S,
    ):
        fields[_clean(k)] = _clean(v)
    secs = _sections(_ckec(html))
    duties = secs.get("工作職責", "")
    others = secs.get("其他", "")
    description = duties
    deadline = _deadline(fields.get("截止日期", ""))
    extra = []
    if fields.get("服務種類"):
        extra.append("服務種類：" + fields["服務種類"])
    if deadline:
        extra.append("截止申請日期：" + deadline)
    if others:
        extra.append(others)
    if extra:
        description = (description + "\n\n" + "\n".join(extra)).strip()
    employment = ""
    blob = " ".join(secs.values())
    if "合約" in blob:
        employment = "合約"
    elif "兼職" in title or "半職" in title:
        employment = "兼職/半職"
    return {
        "source": SOURCE,
        "external_id": path.rstrip("/").split("/")[-1],
        "title": title,
        "company": SOURCE_NAME,
        "salary": "",
        "location": fields.get("工作地區", ""),
        "employment": employment,
        "level": level,
        "posted_date": "",
        "description": description,
        "requirements": secs.get("入職要求", ""),
        "apply_url": DETAIL_URL.format(path=path),
        "logo_url": None,
    }


def scrape():
    html = http.fetch(LIST_URL)
    if not html:
        raise RuntimeError("PLK list page fetch failed")
    jobs = []
    for path, txt in parse_list(html):
        if not classify(txt):
            continue
        detail = http.fetch(DETAIL_URL.format(path=path))
        if not detail:
            continue
        job = parse_detail(detail, path)
        if job:
            jobs.append(job)
    return jobs
