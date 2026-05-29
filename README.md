# Where Did My Day Go

A local-only **macOS** focus & usage dashboard. (Not to be confused with
macOS's built-in *Activity Monitor.app*, which is a process inspector — this
project answers "what apps am I spending my time in?", not "what's eating my
CPU?")

Two pieces:

- **collector.py** — samples the focused app, window title, active Chrome
  tab URL, and idle time every 5 seconds; collapses consecutive identical
  samples into intervals stored in SQLite.
- **server.py** — Flask web app that reads the SQLite DB and renders a
  dashboard with a 24-hour timeline, hourly stacked breakdown, category
  donut, top apps, and top Chrome tabs.

Everything stays on your machine. Nothing is sent anywhere. See [Privacy](#privacy) below.

> **macOS only.** The collector uses LaunchServices, AppleScript, and
> Quartz to read the focused app, window title, and idle time. Porting to
> Windows or Linux means writing a new platform backend — see
> [Cross-platform notes](#cross-platform-notes).

## Prerequisites

- macOS 13+ (tested on Sonoma + Sequoia)
- [**uv**](https://github.com/astral-sh/uv) — Python project manager. Install with:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- Python 3.12+ (uv will install one for you if missing)

## Quick start

```bash
git clone <this-repo> where-did-my-day-go
cd where-did-my-day-go

# Install the launchd auto-start agent. Substitutes this checkout's
# absolute path into the plist and loads it. Runs at every login.
./install_launchd.sh

# Start the dashboard.
./start_server.sh
```

Open **http://127.0.0.1:5173** in your browser.

The first time the collector runs, macOS will prompt for two permissions:

1. **Accessibility** — needed for window titles via System Events.
   System Settings → Privacy & Security → Accessibility → enable the entry
   for `Python` (or for your terminal app, if you ran `start_collector.sh`
   manually).
2. **Automation → Google Chrome** — needed for the active tab URL. You'll
   see a prompt the first time the collector samples Chrome.

If you skip `install_launchd.sh`, run the collector by hand in a separate
terminal with `./start_collector.sh`.

## Configuration

All knobs are environment variables. Defaults work fine for most people.

| Variable               | Default                       | Meaning                                          |
|------------------------|-------------------------------|--------------------------------------------------|
| `SAMPLE_INTERVAL`      | `5`                           | Seconds between collector samples.               |
| `IDLE_THRESHOLD`       | `60`                          | Seconds without keyboard/mouse before "idle".    |
| `PORT`                 | `5173`                        | Dashboard server port.                           |
| `DASHBOARD_URL_PREFIX` | `http://127.0.0.1:$PORT`      | Chrome tabs matching this become category `dashboard` (so opening the dashboard doesn't count as "chrome" time). |
| `ACTIVITY_DB`          | `./activity.db`               | Path to the SQLite database.                     |

Example — run the dashboard on a different port and sample more often:

```bash
PORT=8080 SAMPLE_INTERVAL=2 ./start_server.sh
```

For launchd to pick these up, edit the rendered plist at
`~/Library/LaunchAgents/com.user.wheredidmydaygo.plist` and add an
`<EnvironmentVariables>` block, then re-`launchctl load -w`.

## How tracking works

The collector samples the **focused app** (what the macOS menu bar shows),
not the topmost visible window. This means apps used briefly via ⌘-Tab,
the Finder Dock icon, etc. are correctly attributed even when other
windows are visually on top. Implementation uses `lsappinfo front` —
see [collector.py:`get_frontmost_app`](collector.py).

### Built-in categories

| Category         | How it's detected                                                |
|------------------|------------------------------------------------------------------|
| Claude desktop   | Bundle id `com.anthropic.claude*`                                |
| Claude Code      | Terminal frontmost AND window title contains "claude"            |
| ChatGPT          | Bundle id `com.openai.chat`                                      |
| Chrome           | App `Google Chrome` — also captures active tab URL via AppleScript |
| Dashboard (meta) | Chrome tab URL matching `DASHBOARD_URL_PREFIX`                   |
| VS Code / Cursor | Bundle id / app name                                             |
| Terminal         | Terminal, iTerm2, Warp, Ghostty, Hyper                           |
| Office           | Excel, Word, PowerPoint, Outlook                                 |
| Media            | VLC, OBS, QuickTime, Preview                                     |
| Communication    | Slack, Discord, Messages, Mail                                   |
| Other            | Finder, Postman, Spotify, Figma, Notion, Calendar, Xcode, Safari, Firefox… |
| Idle             | No keyboard/mouse input for ≥`IDLE_THRESHOLD` seconds            |
| Other (bucket)   | Anything not in the table above                                  |

### Adding more apps

Two dicts in `collector.py` drive categorization:

```python
CATEGORY_BY_BUNDLE = {
    "com.figma.Desktop":              "figma",
    "com.openai.chat":                "chatgpt",
    # ...
}
CATEGORY_BY_NAME = {           # fallback by lowercased app name
    "figma": "figma",
    # ...
}
```

To add an app:

1. Find its bundle id:
   ```bash
   osascript -e 'id of app "Spotify"'
   # → com.spotify.client
   ```
   Or: open the app, then `lsappinfo info $(lsappinfo front)`.
2. Add an entry to `CATEGORY_BY_BUNDLE` (preferred) and/or `CATEGORY_BY_NAME`.
3. To get its own color/legend entry on the dashboard, add to three places:
   - `static/styles.css` — a `--c-yourcat: #hex;` line under `:root`
   - `static/app.js` — `CATEGORY_COLORS` and `CATEGORY_LABELS` entries, plus a slot in the `ORDER` array
4. Restart the collector and refresh the dashboard.

Apps without a mapping fall into `"other"` — they still appear in the
**Top apps** table by name, just without their own donut slice.

## Privacy

**Everything stays local.** Neither the collector nor the dashboard makes
any outbound network requests.

That said, the database (`activity.db`) is sensitive — it logs:

- Every **app** you've used, with start/end timestamps.
- Every **window title** of the focused window (e.g. document names,
  Slack channel names, email subjects when shown in the title).
- Every **Chrome tab URL** you've focused (including query strings).
- Every **idle period** ≥ `IDLE_THRESHOLD`.

The DB is **never committed** (it's in `.gitignore`), but treat it like
any other personal log file:

- Don't sync the project directory to a shared cloud folder unless you're
  comfortable with the DB going along for the ride.
- `*.log` files are also gitignored — error traces can include window
  titles and URLs.
- To wipe everything: `./uninstall.sh --purge`

To inspect what's in the DB yourself:

```bash
sqlite3 activity.db "
SELECT datetime(start_ts,'unixepoch','localtime'), category, app_name, chrome_url
FROM activity ORDER BY start_ts DESC LIMIT 50;"
```

## Uninstall

```bash
./uninstall.sh           # unload launchd agent, remove venv. Keeps DB and logs.
./uninstall.sh --purge   # also delete activity.db and *.log files.
rm -rf /path/to/where-did-my-day-go   # remove the checkout itself
```

## File layout

```
where-did-my-day-go/
├── README.md
├── pyproject.toml                     # uv-managed deps
├── .python-version                    # 3.12
├── collector.py                       # sampling loop
├── server.py                          # Flask app
├── db.py                              # SQLite schema + queries
├── start_collector.sh                 # `uv sync` + run collector
├── start_server.sh                    # `uv sync` + run server
├── install_launchd.sh                 # installs the launchd agent
├── uninstall.sh                       # unloads agent (+ optionally purges data)
├── com.user.wheredidmydaygo.plist     # launchd job (template, __PROJECT_DIR__)
├── templates/dashboard.html
├── static/
│   ├── app.js
│   └── styles.css
└── activity.db                        # created at runtime, gitignored
```

## DB schema

A single table, `activity`. Each row is one interval — the collector
extends `end_ts` while the current sample matches the prior key
`(category, app_name, bundle_id, chrome_url, is_idle)`. When the key
changes it opens a new row.

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

Query directly with the `sqlite3` CLI:

```bash
sqlite3 activity.db \
  "SELECT category, SUM(end_ts-start_ts)/60 AS minutes
   FROM activity
   WHERE start_ts > strftime('%s','now','-1 day')
   GROUP BY category ORDER BY minutes DESC;"
```

## Troubleshooting

### Won't auto-start after login

```bash
launchctl print gui/$(id -u)/com.user.wheredidmydaygo
```

Check `last exit code`:
- `78: EX_CONFIG` — usually means TCC is blocking. See the
  ["IMPORTANT — do not put this project inside protected folders"](#important--do-not-put-this-project-inside-desktop-documents-or-downloads) note below.
- `127` — `uv` not found on launchd's PATH. The start scripts add common
  install locations, but if you installed uv somewhere unusual, edit
  `start_collector.sh` and prepend its directory to `PATH`.

### IMPORTANT — do not put this project inside ~/Desktop, ~/Documents, or ~/Downloads

macOS Sonoma+ TCC ("Files & Folders" privacy protection) blocks launchd
agents from reading or executing files inside those three folders. The
collector will silently fail with `last exit code = 78: EX_CONFIG` and
the err log file will not even be created.

`install_launchd.sh` refuses to install if it detects this. Move the
project somewhere else first — `~/Code/`, `~/Projects/`, `~/Tools/`,
anywhere in `/opt/`, etc. all work.

### "No Chrome tab data yet"
Open Chrome, focus a window with a tab, then wait for the next sample.
macOS will prompt for Automation permission the first time; accept it.
If denied: System Settings → Privacy & Security → Automation → toggle
Chrome on for the app running the collector.

### Window titles always empty
Grant Accessibility permission to the app running `collector.py` (when
auto-started via launchd this is `Python`).

### Claude Code shows up as `terminal`
Your terminal's window title doesn't contain "claude". Most terminals
show the running command in the title; if yours doesn't, enable that or
rename the tab manually.

## Cross-platform notes

This project is macOS-only by design — the collector relies on:

- `lsappinfo` (LaunchServices) for the focused app
- AppleScript for the Chrome active tab URL
- `Quartz.CGEventSourceSecondsSinceLastEventType` for idle time
- launchd for auto-start

A Windows or Linux port is feasible but means re-implementing the
collector against `win32api` (Windows) or X11/Wayland (Linux), and
querying Chrome's DevTools Protocol for the active tab. The dashboard
(Flask + SQLite) and the frontend would work as-is. Contributions welcome.


  ## Privacy

  This is the only section of the post where I'm going to ask you to take the
  phrase "local-first" seriously, because everywhere else on the internet it's
  been worn smooth into a marketing word.

  ### What "local-only" actually means here

  Two processes run on your machine. The **collector** writes to a SQLite file
  in the project directory. The **dashboard server** reads from that same
  SQLite file and serves HTTP on `127.0.0.1:5173` — bound to loopback, so it
  isn't reachable from another machine on your network, let alone the
  internet. Neither process opens a network connection of any kind.

  You can verify this yourself:

  ```bash
  # Watch the collector for outbound TCP connections for 30 seconds.
  # Expected output: nothing.
  sudo lsof -p $(pgrep -f 'python collector.py' | tail -1) -i -P 2>/dev/null

  There is one small caveat: the dashboard's HTML pulls Chart.js from
  cdn.jsdelivr.net on first page load, so your browser makes one outbound
  request when you open the dashboard. Your activity data never leaves —
  that's the load order: dashboard HTML → Chart.js library file → JSON of
  your data fetched from 127.0.0.1. If you want zero network at all,
  vendor chart.umd.min.js into static/ and change the <script> tag.