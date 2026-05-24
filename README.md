# Activity Monitor

A local-only macOS activity dashboard. Two pieces:

- **collector.py** — samples the frontmost app, window title, active Chrome
  tab URL, and idle time every 5 seconds; collapses consecutive identical
  samples into intervals stored in SQLite.
- **server.py** — Flask web app that reads the SQLite DB and renders a
  dashboard with a 24-hour timeline, hourly stacked breakdown, category
  donut, top apps, and top Chrome tabs.

Everything stays on your machine. Nothing is sent anywhere.

## What gets tracked

| Category         | How it's detected                                                |
|------------------|------------------------------------------------------------------|
| Claude (desktop) | Bundle id `com.anthropic.claude*` or app name "Claude"           |
| Claude Code      | Terminal app frontmost AND window title contains "claude"        |
| Chrome           | App `Google Chrome` — also captures active tab URL via AppleScript |
| VS Code / Cursor | Bundle id / app name                                             |
| Terminal         | Terminal, iTerm2, Warp, Ghostty, Hyper                           |
| Idle             | No keyboard/mouse input for ≥60s (`HIDIdleTime`)                  |
| Other            | Anything not in the categorization table                         |

Edit `CATEGORY_BY_BUNDLE` / `CATEGORY_BY_NAME` in `collector.py` to add more apps.

## Setup

```bash
cd activity-monitor
./start_collector.sh   # one-off: bootstraps .venv and installs deps, then runs
```

On first launch macOS will prompt for permissions:

1. **Accessibility** — needed for window titles via System Events.
   System Settings → Privacy & Security → Accessibility → add Terminal (or your shell).
2. **Automation → Google Chrome** — needed for the active tab URL.
   You'll see a prompt the first time the collector samples Chrome.

In a separate terminal:

```bash
./start_server.sh      # http://127.0.0.1:5173
```

Open the URL in your browser.

## Auto-start the collector at login (launchd)

```bash
./install_launchd.sh
```

This substitutes the absolute path of your checkout into
`com.user.activitymonitor.plist` (which ships with `__PROJECT_DIR__`
placeholders), writes the rendered file to `~/Library/LaunchAgents/`, and
loads it.

Logs land in `collector.err.log` (Python logging defaults to stderr) and
`collector.log` next to the project. To stop:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.activitymonitor.plist
```

If you move the project directory, just re-run `./install_launchd.sh` — it
will unload the old agent and reinstall with the new path. (Also delete
`.venv/` and let `start_collector.sh` rebuild it on next launch.)

### IMPORTANT — do not put this project inside ~/Desktop, ~/Documents, or ~/Downloads

macOS Sonoma+ TCC ("Files & Folders" privacy protection) blocks launchd
agents from reading or executing files inside those three folders. The
collector will silently fail with `last exit code = 78: EX_CONFIG` and the
err log file will not even be created.

Diagnostic — `launchctl print gui/$(id -u)/com.user.activitymonitor` shows:
```
state          = spawn scheduled
last exit code = 78: EX_CONFIG
```
and `ls` of `collector.err.log` says "no such file."

Fix — keep the project outside the protected folders. `~/Code/`,
`~/Projects/`, `~/Tools/`, anywhere in `/opt/`, etc. all work. This project
is configured to live in `~/Code/activity-monitor/`.

## File layout

```
activity-monitor/
├── README.md
├── requirements.txt
├── collector.py                       # sampling loop
├── server.py                          # Flask app
├── db.py                              # SQLite schema + queries
├── start_collector.sh
├── start_server.sh
├── install_launchd.sh                 # installs the launchd agent
├── com.user.activitymonitor.plist     # launchd job (template, __PROJECT_DIR__)
├── templates/dashboard.html
├── static/
│   ├── app.js
│   └── styles.css
└── activity.db                        # created at runtime
```

## DB schema

A single table, `activity`. Each row is one interval — the collector extends
`end_ts` while the current sample matches the prior key
`(category, app_name, bundle_id, chrome_url, is_idle)`. When the key changes
it opens a new row.

```sql
CREATE TABLE activity (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  start_ts      INTEGER NOT NULL,
  end_ts        INTEGER NOT NULL,
  app_name      TEXT    NOT NULL,
  app_bundle_id TEXT,
  window_title  TEXT,
  chrome_url    TEXT,
  category      TEXT    NOT NULL,
  is_idle       INTEGER NOT NULL DEFAULT 0
);
```

Query directly with the `sqlite3` CLI if you want one-off stats:

```bash
sqlite3 activity.db \
  "SELECT category, SUM(end_ts-start_ts)/60 AS minutes
   FROM activity
   WHERE start_ts > strftime('%s','now','-1 day')
   GROUP BY category ORDER BY minutes DESC;"
```

## Tuning

- `SAMPLE_INTERVAL` in `collector.py` — how often to sample (default 5s).
- `IDLE_THRESHOLD` — seconds without input before counting as away (default 60s).

## Troubleshooting

- **"No Chrome tab data yet"** — open Chrome, focus a window with a tab, then
  wait for the next sample. macOS will prompt for Automation permission the
  first time; accept it. If you denied it: System Settings → Privacy & Security
  → Automation → toggle Chrome on for Terminal (or whatever launched the script).
- **Window titles always empty** — grant Accessibility permission to the app
  running `collector.py` (usually Terminal).
- **Claude Code shows up as `terminal`** — your terminal's window title doesn't
  contain "claude". Most terminals show the running command in the title; if
  yours doesn't, enable that or rename the tab manually.
