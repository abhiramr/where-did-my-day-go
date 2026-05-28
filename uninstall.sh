#!/usr/bin/env bash
# Uninstall the Where Did My Day Go collector (and optionally wipe its data).
#
# - Unloads + removes the launchd agent from ~/Library/LaunchAgents/
# - Also removes any leftover agent from the previous name ("activitymonitor")
# - Deletes the project-local .venv if present
# - With --purge: also deletes activity.db and *.log files
#
# Does NOT delete this checkout; remove the directory yourself if desired.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LABEL="com.user.wheredidmydaygo"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LEGACY_PLIST="$HOME/Library/LaunchAgents/com.user.activitymonitor.plist"

PURGE=0
if [ "${1:-}" = "--purge" ]; then
  PURGE=1
fi

# Unload + remove the launchd agent.
if [ -f "$PLIST" ]; then
  echo "Unloading launchd agent..."
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "  removed $PLIST"
else
  echo "  (no launchd agent installed)"
fi

# Also remove the legacy agent if it's still around from before the rename.
if [ -f "$LEGACY_PLIST" ]; then
  echo "Unloading legacy launchd agent..."
  launchctl unload "$LEGACY_PLIST" 2>/dev/null || true
  rm -f "$LEGACY_PLIST"
  echo "  removed $LEGACY_PLIST"
fi

# Remove the local venv.
if [ -d "$PROJECT_DIR/.venv" ]; then
  echo "Removing .venv..."
  rm -rf "$PROJECT_DIR/.venv"
fi

# Remove the activity DB and logs only when explicitly asked.
if [ "$PURGE" -eq 1 ]; then
  echo "Purging local data..."
  rm -f "$PROJECT_DIR/activity.db" "$PROJECT_DIR/activity.db-journal"
  rm -f "$PROJECT_DIR/"*.log
  echo "  activity.db and logs deleted"
else
  echo
  echo "Note: activity.db and logs were kept."
  echo "      To delete them as well, re-run: ./uninstall.sh --purge"
fi

echo
echo "Done. To remove this checkout entirely:  rm -rf \"$PROJECT_DIR\""
