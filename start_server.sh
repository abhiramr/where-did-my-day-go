#!/usr/bin/env bash
# Start the Flask dashboard server.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi

PORT="${PORT:-5173}"
echo "Dashboard: http://127.0.0.1:${PORT}"
exec ./.venv/bin/python server.py
