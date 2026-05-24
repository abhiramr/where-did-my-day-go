#!/usr/bin/env bash
# Start the activity collector in the foreground.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi

exec ./.venv/bin/python collector.py
