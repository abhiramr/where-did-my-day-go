#!/usr/bin/env bash
# Start the activity collector in the foreground.
#
# Uses `uv` to manage the venv + dependencies (see pyproject.toml).
# `uv sync` is idempotent and fast on subsequent runs.
set -euo pipefail
cd "$(dirname "$0")"

# launchd runs with a minimal PATH. Extend it so common `uv` install locations
# are visible. (uv installs to ~/.local/bin by default; Homebrew uses
# /opt/homebrew/bin on Apple Silicon and /usr/local/bin on Intel.)
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: 'uv' not found on PATH." >&2
  echo "       Install with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 127
fi

uv sync --quiet
exec uv run --quiet python collector.py
