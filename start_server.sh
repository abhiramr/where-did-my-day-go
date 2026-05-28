#!/usr/bin/env bash
# Start the Flask dashboard server.
#
# Uses `uv` to manage the venv + dependencies (see pyproject.toml).
set -euo pipefail
cd "$(dirname "$0")"

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH." >&2
  echo "       Install with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 127
fi

uv sync --quiet
PORT="${PORT:-5173}"
echo "Dashboard: http://127.0.0.1:${PORT}"
exec uv run --quiet python server.py
