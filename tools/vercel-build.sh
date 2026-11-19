#!/usr/bin/env bash
# Vercel build: installs the two Python packages and builds the site into public/.
# The URL is the project's production address (e.g. doon-home-guide.vercel.app) unless SITE_URL is set.
set -euo pipefail
python3 -m pip install -q -r requirements.txt 2>/dev/null \
  || python3 -m pip install -q --break-system-packages -r requirements.txt
host="${VERCEL_PROJECT_PRODUCTION_URL:-${VERCEL_URL:-}}"
url="${SITE_URL:-${host:+https://$host}}"
python3 build.py --out public ${url:+--url "$url"}
