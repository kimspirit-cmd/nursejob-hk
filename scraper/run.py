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
import sys
import traceback
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
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    print(f"wrote {DATA_PATH} ({len(all_jobs)} jobs)", flush=True)
    return summary


if __name__ == "__main__":
    srcs = sys.argv[1:] or None
    if srcs == ["all"]:
        srcs = None  # "all" means every source in SCRAPERS
    run(srcs)
