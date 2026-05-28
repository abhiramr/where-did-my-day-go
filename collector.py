"""macOS activity collector.

Samples the frontmost app, window title, Chrome URL, and idle time at a fixed
interval, then collapses consecutive identical samples into intervals in the DB.

Permissions needed (grant when first prompted):
  - Accessibility       -> for window titles via AppleScript / System Events
  - Automation > Chrome -> for the active Chrome tab URL

Run with:
  python3 collector.py
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass

import db

# pyobjc
from AppKit import NSWorkspace, NSRunningApplication  # type: ignore
import Quartz  # type: ignore


# Runtime tunables. Each falls back to a sane default if the env var is unset.
# See README "Configuration" section for details.
SAMPLE_INTERVAL = int(os.environ.get("SAMPLE_INTERVAL", "5"))   # seconds between samples
IDLE_THRESHOLD  = int(os.environ.get("IDLE_THRESHOLD",  "60"))  # seconds without HID input -> "idle"
DASHBOARD_URL_PREFIX = os.environ.get(
    "DASHBOARD_URL_PREFIX",
    f"http://127.0.0.1:{os.environ.get('PORT', '5173')}",
)  # Chrome tabs matching this become category "dashboard"
CHROME_POLL_EVERY = 1    # poll Chrome URL on every sample where Chrome is frontmost

log = logging.getLogger("collector")


# -------- categorization --------

CATEGORY_BY_BUNDLE = {
    "com.anthropic.claudefordesktop": "claude_desktop",
    "com.anthropic.claude":           "claude_desktop",
    "com.openai.chat":                "chatgpt",
    "com.google.Chrome":              "chrome",
    "com.google.Chrome.canary":       "chrome",
    "com.microsoft.VSCode":            "vscode",
    "com.microsoft.VSCodeInsiders":    "vscode",
    "com.todesktop.230313mzl4w4u92":  "cursor",  # Cursor editor
    "com.apple.Terminal":             "terminal",
    "com.googlecode.iterm2":          "terminal",
    "dev.warp.Warp-Stable":           "terminal",
    "com.mitchellh.ghostty":          "terminal",
    "co.zeit.hyper":                  "terminal",
    "com.apple.dt.Xcode":             "xcode",
    "com.tinyspeck.slackmacgap":      "slack",
    "com.hnc.Discord":                "discord",
    "com.apple.MobileSMS":            "messages",
    "com.apple.mail":                 "mail",
    "com.apple.Safari":               "safari",
    "org.mozilla.firefox":            "firefox",
    "com.spotify.client":             "spotify",
    "com.apple.iCal":                 "calendar",
    "com.figma.Desktop":              "figma",
    "notion.id":                      "notion",
    "com.obsproject.obs-studio":      "obs",
    "com.microsoft.Excel":            "excel",
    "com.microsoft.Word":             "word",
    "com.microsoft.Powerpoint":       "powerpoint",
    "com.microsoft.Outlook":          "outlook",
    "com.postmanlabs.mac":            "postman",
    "org.videolan.vlc":               "vlc",
    "com.apple.finder":               "finder",
    "com.apple.Preview":              "preview",
    "com.apple.QuickTimePlayerX":     "quicktime",
}

# fallback by app name (lowercased)
CATEGORY_BY_NAME = {
    "claude":           "claude_desktop",
    "chatgpt":          "chatgpt",
    "openai":           "chatgpt",
    "google chrome":    "chrome",
    "chrome":           "chrome",
    "code":             "vscode",
    "visual studio code": "vscode",
    "cursor":           "cursor",
    "terminal":         "terminal",
    "iterm2":           "terminal",
    "warp":             "terminal",
    "ghostty":          "terminal",
    "hyper":            "terminal",
    "xcode":            "xcode",
    "slack":            "slack",
    "discord":          "discord",
    "messages":         "messages",
    "mail":             "mail",
    "safari":           "safari",
    "firefox":          "firefox",
    "spotify":          "spotify",
    "calendar":         "calendar",
    "figma":            "figma",
    "notion":           "notion",
    "obs":              "obs",
    "obs studio":       "obs",
    "microsoft excel":  "excel",
    "excel":            "excel",
    "microsoft word":   "word",
    "word":             "word",
    "microsoft powerpoint": "powerpoint",
    "powerpoint":       "powerpoint",
    "microsoft outlook": "outlook",
    "outlook":          "outlook",
    "postman":          "postman",
    "vlc":              "vlc",
    "vlc media player": "vlc",
    "finder":           "finder",
    "preview":          "preview",
    "quicktime player": "quicktime",
}

TERMINAL_CATEGORIES = {"terminal"}


def categorize(app_name: str, bundle_id: str | None, window_title: str | None) -> str:
    """Decide a category for a sample.

    Special case: if we're in a terminal and the window title mentions "claude"
    we infer the user is running Claude Code in the terminal.
    """
    base = CATEGORY_BY_BUNDLE.get(bundle_id or "") or CATEGORY_BY_NAME.get(
        (app_name or "").lower(), "other"
    )
    if base in TERMINAL_CATEGORIES and window_title:
        wt = window_title.lower()
        if "claude" in wt and "claude code" not in wt:
            # also catch things like "— claude" in title
            return "claude_code"
        if "claude code" in wt or wt.startswith("claude") or " claude " in wt:
            return "claude_code"
    return base


# -------- macOS lookups --------

def get_idle_seconds() -> float:
    # kCGAnyInputEventType is uint max (0xFFFFFFFF); use the named constant
    # so PyObjC's type-checking is happy.
    return Quartz.CGEventSourceSecondsSinceLastEventType(
        Quartz.kCGEventSourceStateHIDSystemState, Quartz.kCGAnyInputEventType
    )


def _parse_lsappinfo_quoted(s: str) -> str | None:
    """Parse a value out of lsappinfo's `"key"="value"` output."""
    if not s:
        return None
    # value is between the second and third `"`; pick everything after the
    # first `=` then strip surrounding quotes if present.
    eq = s.find("=")
    if eq < 0:
        return None
    val = s[eq + 1 :].strip()
    if len(val) >= 2 and val[0] == '"' and val[-1] == '"':
        val = val[1:-1]
    return val or None


def _lsappinfo_front() -> tuple[str, str | None, int | None] | None:
    """Query macOS's LaunchServices for the user-active app.

    Returns (name, bundle_id, pid) or None on failure.

    `lsappinfo front` returns the ASN of the user-focused app — this is the
    same notion of "front" macOS itself uses (menu bar / keyboard focus), and
    crucially is *not* the same as "topmost on-screen window". A backgrounded
    Chrome window can sit visually on top of an active Finder/Claude window;
    CGWindowListCopyWindowInfo would pick Chrome, but lsappinfo correctly
    picks the focused app.
    """
    try:
        asn = subprocess.run(
            ["/usr/bin/lsappinfo", "front"],
            capture_output=True, text=True, timeout=1.0,
        ).stdout.strip()
        if not asn:
            return None
        out = subprocess.run(
            ["/usr/bin/lsappinfo", "info",
             "-only", "name", "-only", "bundleID", "-only", "pid", asn],
            capture_output=True, text=True, timeout=1.0,
        ).stdout
    except Exception:
        return None

    name = bundle = pid_s = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('"LSDisplayName"') or line.startswith('"name"'):
            name = _parse_lsappinfo_quoted(line)
        elif line.startswith('"CFBundleIdentifier"') or line.startswith('"bundleID"'):
            bundle = _parse_lsappinfo_quoted(line)
        elif line.startswith('"pid"'):
            pid_s = _parse_lsappinfo_quoted(line)

    pid_i = None
    if pid_s and pid_s.isdigit():
        pid_i = int(pid_s)
    if not name and not pid_i:
        return None
    return (name or "", bundle, pid_i)


def _cgwindowlist_topmost() -> tuple[str, str | None, int | None] | None:
    """Fallback: topmost on-screen layer-0 window's owner app."""
    try:
        opts = (
            Quartz.kCGWindowListOptionOnScreenOnly
            | Quartz.kCGWindowListExcludeDesktopElements
        )
        windows = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID) or []
        for w in windows:
            if w.get("kCGWindowLayer", 0) != 0:
                continue
            pid = w.get("kCGWindowOwnerPID")
            owner = w.get("kCGWindowOwnerName") or ""
            if not pid:
                continue
            bundle_id = None
            name = str(owner)
            try:
                running = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
                if running is not None:
                    bid = running.bundleIdentifier()
                    if bid:
                        bundle_id = str(bid)
                    ln = running.localizedName()
                    if ln:
                        name = str(ln)
            except Exception:
                pass
            return name, bundle_id, int(pid)
    except Exception:
        log.debug("CGWindowList frontmost lookup failed", exc_info=True)
    return None


def get_frontmost_app() -> tuple[str, str | None, int | None]:
    """Returns (app_name, bundle_id, pid) of the user-focused app.

    Primary signal: `lsappinfo front` — LaunchServices' authoritative notion
    of which app currently has keyboard / menu-bar focus. Fresh per call (it's
    a subprocess), so no run-loop staleness issues.

    Fallback: CGWindowList topmost window owner. Only used if lsappinfo fails
    (e.g. binary not present, malformed output). NSWorkspace.frontmostApplication
    is *not* used as a fallback — it relies on AppKit notifications and gets
    frozen in long-running non-NSApp processes.
    """
    res = _lsappinfo_front()
    if res is not None:
        return res
    res = _cgwindowlist_topmost()
    if res is not None:
        return res
    return "", None, None


def get_window_title(pid: int | None) -> str | None:
    """Try CGWindowListCopyWindowInfo first (no AX perm), fallback to AppleScript."""
    if pid is None:
        return None
    try:
        opts = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        windows = Quartz.CGWindowListCopyWindowInfo(opts, Quartz.kCGNullWindowID)
        # frontmost on-screen window for this pid with non-empty name
        for w in windows:
            if w.get("kCGWindowOwnerPID") == pid and w.get("kCGWindowLayer", 0) == 0:
                name = w.get("kCGWindowName")
                if name:
                    return str(name)
    except Exception as e:
        log.debug("CGWindowList failed: %s", e)

    # AppleScript fallback (needs Accessibility permission)
    try:
        script = (
            'tell application "System Events"\n'
            '  try\n'
            '    set frontApp to first application process whose frontmost is true\n'
            '    return name of front window of frontApp\n'
            '  on error\n'
            '    return ""\n'
            '  end try\n'
            'end tell'
        )
        out = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=2,
        )
        title = out.stdout.strip()
        return title or None
    except Exception as e:
        log.debug("AppleScript title failed: %s", e)
        return None


_CHROME_SCRIPT = (
    'tell application "Google Chrome"\n'
    '  if it is running and (count of windows) > 0 then\n'
    '    try\n'
    '      set theTab to active tab of front window\n'
    '      set theURL to URL of theTab\n'
    '      set theTitle to title of theTab\n'
    '      return theURL & "||" & theTitle\n'
    '    on error\n'
    '      return ""\n'
    '    end try\n'
    '  else\n'
    '    return ""\n'
    '  end if\n'
    'end tell'
)


def get_chrome_active() -> tuple[str | None, str | None]:
    try:
        out = subprocess.run(
            ["osascript", "-e", _CHROME_SCRIPT],
            capture_output=True, text=True, timeout=2,
        )
        raw = out.stdout.strip()
        if not raw or "||" not in raw:
            return None, None
        url, _, title = raw.partition("||")
        return (url or None), (title or None)
    except Exception as e:
        log.debug("Chrome script failed: %s", e)
        return None, None


# -------- main loop --------

@dataclass
class Sample:
    ts: int
    app_name: str
    bundle_id: str | None
    window_title: str | None
    chrome_url: str | None
    category: str
    is_idle: bool

    def key(self) -> tuple:
        # what makes two samples count as the "same interval"
        return (self.category, self.app_name, self.bundle_id, self.chrome_url, self.is_idle)


def take_sample() -> Sample:
    ts = int(time.time())
    idle_s = get_idle_seconds()
    is_idle = idle_s >= IDLE_THRESHOLD

    if is_idle:
        return Sample(
            ts=ts, app_name="(idle)", bundle_id=None, window_title=None,
            chrome_url=None, category="idle", is_idle=True,
        )

    app_name, bundle_id, pid = get_frontmost_app()
    window_title = get_window_title(pid)

    chrome_url = None
    cat = categorize(app_name, bundle_id, window_title)
    if cat == "chrome":
        url, ctitle = get_chrome_active()
        chrome_url = url
        # prefer the chrome tab title over the generic window title
        if ctitle:
            window_title = ctitle
        # the dashboard tab is "meta" — track it separately so it doesn't
        # inflate real-browsing Chrome stats
        if url and url.startswith(DASHBOARD_URL_PREFIX):
            cat = "dashboard"

    return Sample(
        ts=ts,
        app_name=app_name or "(unknown)",
        bundle_id=bundle_id,
        window_title=window_title,
        chrome_url=chrome_url,
        category=cat,
        is_idle=False,
    )


_stop = False


def _sig_handler(signum, _frame):
    global _stop
    log.info("Received signal %s, shutting down", signum)
    _stop = True


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    db.init_db()
    log.info("Collector starting, sampling every %ss, idle threshold %ss",
             SAMPLE_INTERVAL, IDLE_THRESHOLD)

    last_row = db.last_interval()
    last_key = None
    last_id = None
    last_end_ts: int | None = None
    if last_row is not None:
        # only resume the previous interval if it ended within one sample window
        if int(time.time()) - last_row["end_ts"] <= SAMPLE_INTERVAL * 2:
            last_id = last_row["id"]
            last_key = (
                last_row["category"], last_row["app_name"],
                last_row["app_bundle_id"], last_row["chrome_url"],
                bool(last_row["is_idle"]),
            )
            last_end_ts = last_row["end_ts"]

    while not _stop:
        try:
            s = take_sample()
            if s.key() == last_key and last_id is not None:
                db.extend_interval(last_id, s.ts, s.window_title)
                last_end_ts = s.ts
                log.debug("· %s | %s", s.category, s.app_name)
            else:
                # Key changed. Close the gap between the previous row and this
                # observation, but only when the gap looks like a normal app
                # switch (not a machine-sleep or collector-restart gap). This
                # eliminates SAMPLE_INTERVAL-sized holes at every key change.
                if last_id is not None and last_end_ts is not None:
                    gap = s.ts - last_end_ts
                    if 0 < gap <= SAMPLE_INTERVAL * 2:
                        db.extend_interval(last_id, s.ts, None)
                last_id = db.insert_interval(
                    start_ts=s.ts,
                    end_ts=s.ts + SAMPLE_INTERVAL,
                    app_name=s.app_name,
                    app_bundle_id=s.bundle_id,
                    window_title=s.window_title,
                    chrome_url=s.chrome_url,
                    category=s.category,
                    is_idle=s.is_idle,
                )
                last_key = s.key()
                last_end_ts = s.ts + SAMPLE_INTERVAL
                log.info("→ %s | %s | url=%s | title=%s",
                         s.category, s.app_name,
                         (s.chrome_url or "—"),
                         (s.window_title or "")[:80])
        except Exception:
            log.exception("Sample loop error")

        # sleep but stay responsive to SIGTERM
        for _ in range(SAMPLE_INTERVAL):
            if _stop:
                break
            time.sleep(1)

    log.info("Collector stopped")


if __name__ == "__main__":
    sys.exit(run())
