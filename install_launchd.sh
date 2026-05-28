#!/usr/bin/env bash
# Install the Where Did My Day Go collector as a launchd user agent.
#
# Reads com.user.wheredidmydaygo.plist (a template with __PROJECT_DIR__
# placeholders), substitutes the absolute path of this checkout, writes the
# result to ~/Library/LaunchAgents/, and loads it.
#
# Re-running this script is safe — it will unload an existing instance first.
# Also cleans up any leftover agent from the project's previous name
# ("activitymonitor") if present.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$PROJECT_DIR/com.user.wheredidmydaygo.plist"
LABEL="com.user.wheredidmydaygo"
TARGET="$HOME/Library/LaunchAgents/${LABEL}.plist"
LEGACY_PLIST="$HOME/Library/LaunchAgents/com.user.activitymonitor.plist"

if [ ! -f "$TEMPLATE" ]; then
  echo "error: template not found at $TEMPLATE" >&2
  exit 1
fi

case "$PROJECT_DIR" in
  "$HOME/Desktop"/*|"$HOME/Documents"/*|"$HOME/Downloads"/*)
    echo "error: project is inside a TCC-protected folder ($PROJECT_DIR)." >&2
    echo "       launchd cannot execute scripts from ~/Desktop, ~/Documents," >&2
    echo "       or ~/Downloads. Move the project to e.g. ~/Code/ first." >&2
    exit 2
    ;;
esac

mkdir -p "$HOME/Library/LaunchAgents"

# Clean up the project's previous launchd identity if it's still installed.
if [ -f "$LEGACY_PLIST" ]; then
  echo "Removing legacy agent at $LEGACY_PLIST..."
  launchctl unload "$LEGACY_PLIST" 2>/dev/null || true
  rm -f "$LEGACY_PLIST"
fi

# Unload any previously installed instance (ignore errors if not loaded).
if [ -f "$TARGET" ]; then
  launchctl unload "$TARGET" 2>/dev/null || true
fi

# Substitute placeholder. Using a sentinel that can't appear in any real path.
sed "s|__PROJECT_DIR__|${PROJECT_DIR}|g" "$TEMPLATE" > "$TARGET"

launchctl load -w "$TARGET"

echo "Installed: $TARGET"
echo "Status:    launchctl list | grep ${LABEL}"
echo "Logs:      $PROJECT_DIR/collector.log, collector.err.log"
echo "Uninstall: launchctl unload \"$TARGET\" && rm \"$TARGET\""
