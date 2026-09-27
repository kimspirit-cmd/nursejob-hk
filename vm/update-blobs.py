#!/usr/bin/env python3
"""Update Netlify Blobs with fresh nurse jobs (0 Netlify credit).

Runs the Python scraper + site builder, then pushes dist/jobs.json to
Netlify Blobs (store "jobs", key "latest").

Usage:
  update-blobs.py --force        # always scrape + push (daily cron)
  update-blobs.py --check        # only scrape+push if a refresh was requested
                                 # via the website button (Blobs refresh-request flag)

A lock file prevents overlapping runs.
"""
import datetime
import fcntl
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blobs

LOCK = os.path.join(ROOT, "vm", ".update.lock")
DIST_JOBS = os.path.join(ROOT, "dist", "jobs.json")


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
        "updatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "jobs": jobs,
    }
    blobs.set_json("latest", payload)
    # Clear any pending manual refresh request.
    try:
        blobs.delete("refresh-request")
    except Exception as e:
        print(f"note: could not clear refresh-request: {e}")
    print(f"=== pushed {len(jobs)} jobs to Blobs ===", flush=True)


def refresh_requested():
    flag = blobs.get_json("refresh-request")
    if not flag or not flag.get("requestedAt"):
        return False
    latest = blobs.get_json("latest") or {}
    # Requested after the last successful push?
    return flag["requestedAt"] > (latest.get("updatedAt") or "")


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
