"""Stateless orchestrator: scrape all sources -> write data/jobs.json.

No SQLite: output is a single JSON file so the pipeline can run on
ephemeral build environments (e.g. Netlify build).

Per-source fallback: the PREVIOUS committed data/jobs.json is loaded first;
if a source returns fetched=0 (or raises), that source's jobs are reused
from the previous file instead of being wiped.

Usage: python3 scraper/run.py [all|gov|jump|ctgoodjobs|csb|plk ...]
"""
import json
import os
import re
import sys
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone

# Allow running as `python3 scraper/run.py` (script mode) as well as
# `python3 -m scraper.run` (package mode).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scraper import gov, jump, ctgoodjobs, csb, plk, tungwah, caritas  # noqa: E402
from scraper import clean_text  # noqa: E402

HKT = timezone(timedelta(hours=8))
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "jobs.json")

SCRAPERS = [
    ("gov", gov, gov.SOURCE_NAME),
    ("jump", jump, jump.SOURCE_NAME),
    ("ctgoodjobs", ctgoodjobs, ctgoodjobs.SOURCE_NAME),
    ("csb", csb, csb.SOURCE_NAME),
    ("plk", plk, plk.SOURCE_NAME),
    ("tungwah", tungwah, tungwah.SOURCE_NAME),
    ("caritas", caritas, caritas.SOURCE_NAME),
]

# Fields every job dict carries through the pipeline (mirrors the old DB row).
JOB_FIELDS = ("source", "external_id", "title", "company", "salary", "location",
              "employment", "level", "posted_date", "description", "requirements",
              "apply_url", "logo_url")


def _clean_job(job: dict) -> dict:
    """Keep known fields; normalize free text (central anti-junk defense)."""
    out = {f: job.get(f, "") for f in JOB_FIELDS}
    out["description"] = clean_text(out.get("description"))
    out["requirements"] = clean_text(out.get("requirements"))
    return out


# --- 0-credit optimization: slim / dedup / expiry / stats (run.py only) ---

MAX_DESC_CHARS = 200
EXPIRY_DAYS = 30


def _slim_description(text: str) -> str:
    """Strip any HTML tags, collapse whitespace, keep first 200 chars."""
    t = re.sub(r"<[^>]+>", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > MAX_DESC_CHARS:
        t = t[:MAX_DESC_CHARS].rstrip() + "..."
    return t


def _parse_posted(date_str: str):
    """Return date object or None if missing/unparseable (treated as valid)."""
    if not date_str or not str(date_str).strip():
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(date_str).strip()[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(date_str).strip()).date()
    except ValueError:
        return None


def _dedup_key(job: dict) -> tuple:
    # district proxy: location field (no separate district column exists)
    return (
        str(job.get("title", "")).strip().lower(),
        str(job.get("company", "")).strip().lower(),
        str(job.get("location", "")).strip().lower(),
    )


def optimize(jobs: list) -> tuple:
    """Slim descriptions, dedup, drop expired. Returns (jobs, report)."""
    before = len(jobs)
    # 1. slim descriptions (+ defensive base64 strip, logo stays null)
    for j in jobs:
        j["description"] = _slim_description(j.get("description", ""))
        j["requirements"] = _slim_description(j.get("requirements", ""))
        if j.get("logo_url"):
            j["logo_url"] = None
    # 2. dedup: keep newest posted_date per (title, company, location)
    best: dict = {}
    for j in jobs:
        k = _dedup_key(j)
        cur = best.get(k)
        if cur is None:
            best[k] = j
        else:
            d_new = _parse_posted(j.get("posted_date"))
            d_cur = _parse_posted(cur.get("posted_date"))
            if d_new and (not d_cur or d_new > d_cur):
                best[k] = j
    deduped = list(best.values())
    # 3. expiry: drop posted_date older than 30 days; missing = keep
    today = datetime.now(HKT).date()
    kept = []
    expired = 0
    for j in deduped:
        d = _parse_posted(j.get("posted_date"))
        if d and (today - d).days > EXPIRY_DAYS:
            expired += 1
            continue
        kept.append(j)
    report = {"before": before, "deduped": len(deduped), "expired": expired,
              "after": len(kept)}
    return kept, report


def load_previous() -> dict:
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": "", "jobs": [], "sources": {}}


def run(sources: list | None = None) -> dict:
    previous = load_previous()
    prev_by_source: dict = {}
    for j in previous.get("jobs", []):
        prev_by_source.setdefault(j.get("source"), []).append(j)

    all_jobs: list = []
    summary: dict = {}
    for key, mod, name in SCRAPERS:
        if sources and key not in sources:
            continue
        fetched = 0
        note = ""
        jobs: list = []
        try:
            raw = mod.scrape()
            fetched = len(raw)
            if not raw:
                note = "EMPTY RESULT - reused previous data for this source"
                print(f"[{key}] WARNING: scraper returned 0 jobs; "
                      f"reusing previous data", flush=True)
                jobs = prev_by_source.get(key, [])
            else:
                jobs = [_clean_job(j) for j in raw]
        except Exception as e:  # noqa: BLE001 - keep other sources running
            note = f"ERROR: {e} - reused previous data for this source"
            traceback.print_exc()
            jobs = prev_by_source.get(key, [])
        all_jobs.extend(jobs)
        summary[key] = {"fetched": fetched, "jobs": len(jobs), "note": note}
        print(f"[{key}] {name}: fetched={fetched} kept={len(jobs)} {note}",
              flush=True)

    payload = {
        "updated_at": datetime.now(HKT).isoformat(timespec="seconds"),
        "jobs": all_jobs,
        "sources": summary,
    }
    # 0-credit optimization: slim + dedup + expiry, then attach stats
    all_jobs, opt = optimize(all_jobs)
    payload["jobs"] = all_jobs
    payload["stats"] = {
        "total": len(all_jobs),
        "bySource": dict(Counter(j.get("source", "") for j in all_jobs)),
        "byDistrict": dict(Counter(
            (j.get("location") or "").strip() or "未註明" for j in all_jobs)),
        "updatedAt": datetime.now(HKT).strftime("%Y-%m-%d %H:%M HKT"),
    }
    print(f"[optimize] before={opt['before']} deduped={opt['deduped']} "
          f"expired={opt['expired']} after={opt['after']}", flush=True)
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    size_kb = os.path.getsize(DATA_PATH) / 1024
    print(f"wrote {DATA_PATH} ({len(all_jobs)} jobs, {size_kb:.1f} KB)",
          flush=True)
    return summary


if __name__ == "__main__":
    srcs = sys.argv[1:] or None
    if srcs == ["all"]:
        srcs = None  # "all" means every source in SCRAPERS
    run(srcs)
