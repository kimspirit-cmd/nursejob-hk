#!/usr/bin/env bash
# Netlify build: scrape 5 sources -> build static site.
set -euo pipefail
pip install -q -r requirements.txt
python3 scraper/run.py
python3 site/build.py
