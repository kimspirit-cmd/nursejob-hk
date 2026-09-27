#!/usr/bin/env python3
"""Update Netlify Blobs with fresh nurse jobs (0 Netlify credit).

Runs the Python scraper + site builder, then POSTs dist/jobs.json to the
Netlify function `update-jobs` (which writes to Blobs via @netlify/blobs,
guaranteeing the same Blobs context as `get-jobs`).

Usage:
  update-blobs.py --force        # always scrape + push (daily cron)
  update-blobs.py --check        # only scrape+push if a refresh was requested
                                 # via the website button (checks via update-jobs)

A lock file prevents overlapping runs.
The shared secret lives in vm/.update-secret (gitignored, not committed).
"""
import datetime
import fcntl
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET_FILE = os.path.join(ROOT, "vm", ".update-secret")
LOCK = os.path.join(ROOT, "vm", ".update.lock")
DIST_JOBS = os.path.join(ROOT, "dist", "jobs.json")
UPDATE_URL = "https://nursejobhk.netlify.app/.netlify/functions/update-jobs"


def _secret():
    with open(SECRET_FILE, encoding="utf-8") as f:
        return f.read().strip()


def _post(payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        UPDATE_URL, data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")
        if resp.status != 200:
            raise RuntimeError(f"update-jobs HTTP {resp.status}: {body}")
        return json.loads(body)


def run(cmd):
    print(f"$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}")


def do_update(reason):
    print(f"=== update-blobs ({reason}) {datetime.datetime.now().isoformat()} ===", flush=True)
    run([sys.executable, "scraper/run.py"])
    run([sys.executable, "site/build.py"])
    with open(DIST_JOBS, encoding="utf-8") as f:
        jobs = json.load(f)
    if not isinstance(jobs, list) or not jobs:
        raise RuntimeError("dist/jobs.json is empty or invalid; refusing to push")
    payload = {
        "secret": _secret(),
        "action": "update",
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "jobs": jobs,
    }
    result = _post(payload)
    print(f"=== pushed {result.get('count', len(jobs))} jobs to Blobs ===", flush=True)


def refresh_requested():
    result = _post({"secret": _secret(), "action": "check"})
    return bool(result.get("refreshRequested"))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    with open(LOCK, "w") as lockf:
        try:
            fcntl.flock(lockf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print("another update is running; exiting")
            return 0
        try:
            if mode == "--force":
                do_update("scheduled")
            elif mode == "--check":
                if refresh_requested():
                    do_update("manual button")
                else:
                    print("no refresh requested; skipping")
            else:
                print(f"unknown mode: {mode}", file=sys.stderr)
                return 2
        finally:
            fcntl.flock(lockf, fcntl.LOCK_UN)
    return 0


if __name__ == "__main__":
    sys.exit(main())
