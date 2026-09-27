#!/usr/bin/env bash
# Netlify build: scrape 5 sources -> build static site.
set -euo pipefail
pip install -q -r requirements.txt
# Version badge: inject version + commit + build time + branch for dist/version.json
# and window.__APP_VERSION__ (used by the footer version badge).
export APP_VERSION="$(python3 -c "import json; print(json.load(open('src/version.json'))['version'])")"
export GIT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export BUILD_TIME="$(date '+%Y-%m-%d %H:%M')"
export APP_BRANCH="${BRANCH:-$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)}"
python3 scraper/run.py
python3 site/build.py
