"""SQLite schema and helpers for the activity monitor.

Stores activity as intervals: when the (category, app, url, idle) key changes,
we close the current row and open a new one. This keeps the DB compact and
makes aggregate queries cheap.
"""
from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("ACTIVITY_DB", Path(__file__).parent / "activity.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity (
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
CREATE INDEX IF NOT EXISTS idx_activity_start    ON activity(start_ts);
CREATE INDEX IF NOT EXISTS idx_activity_end      ON activity(end_ts);
CREATE INDEX IF NOT EXISTS idx_activity_category ON activity(category);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def cursor():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- writes ---

def insert_interval(
    start_ts: int,
    end_ts: int,
    app_name: str,
    app_bundle_id: str | None,
    window_title: str | None,
    chrome_url: str | None,
    category: str,
    is_idle: bool,
) -> int:
    with cursor() as conn:
        cur = conn.execute(
            """INSERT INTO activity
               (start_ts, end_ts, app_name, app_bundle_id, window_title,
                chrome_url, category, is_idle)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (start_ts, end_ts, app_name, app_bundle_id, window_title,
             chrome_url, category, 1 if is_idle else 0),
        )
        return cur.lastrowid


def extend_interval(row_id: int, end_ts: int, window_title: str | None) -> None:
    with cursor() as conn:
        conn.execute(
            "UPDATE activity SET end_ts = ?, window_title = COALESCE(?, window_title) WHERE id = ?",
            (end_ts, window_title, row_id),
        )


def last_interval() -> sqlite3.Row | None:
    with cursor() as conn:
        return conn.execute(
            "SELECT * FROM activity ORDER BY id DESC LIMIT 1"
        ).fetchone()


# --- reads (dashboard) ---

def day_bounds(date_str: str) -> tuple[int, int]:
    """date_str = 'YYYY-MM-DD' in local time -> (start_epoch, end_epoch)."""
    t = time.strptime(date_str, "%Y-%m-%d")
    start = int(time.mktime(t))
    end = start + 86400
    return start, end


def intervals_in_range(start_ts: int, end_ts: int) -> list[dict]:
    with cursor() as conn:
        rows = conn.execute(
            """SELECT id, start_ts, end_ts, app_name, app_bundle_id,
                      window_title, chrome_url, category, is_idle
               FROM activity
               WHERE end_ts > ? AND start_ts < ?
               ORDER BY start_ts ASC""",
            (start_ts, end_ts),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        # clip to range
        d["start_ts"] = max(d["start_ts"], start_ts)
        d["end_ts"] = min(d["end_ts"], end_ts)
        d["duration"] = d["end_ts"] - d["start_ts"]
        out.append(d)
    return out


def totals_by_category(start_ts: int, end_ts: int) -> list[dict]:
    with cursor() as conn:
        rows = conn.execute(
            """SELECT category,
                      SUM(MIN(end_ts, ?) - MAX(start_ts, ?)) AS seconds
               FROM activity
               WHERE end_ts > ? AND start_ts < ?
               GROUP BY category
               ORDER BY seconds DESC""",
            (end_ts, start_ts, start_ts, end_ts),
        ).fetchall()
    return [dict(r) for r in rows]


def totals_by_app(start_ts: int, end_ts: int, limit: int = 20) -> list[dict]:
    with cursor() as conn:
        rows = conn.execute(
            """SELECT app_name, category,
                      SUM(MIN(end_ts, ?) - MAX(start_ts, ?)) AS seconds
               FROM activity
               WHERE end_ts > ? AND start_ts < ? AND is_idle = 0
               GROUP BY app_name, category
               ORDER BY seconds DESC
               LIMIT ?""",
            (end_ts, start_ts, start_ts, end_ts, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def top_chrome_urls(start_ts: int, end_ts: int, limit: int = 15) -> list[dict]:
    with cursor() as conn:
        rows = conn.execute(
            """SELECT chrome_url,
                      SUM(MIN(end_ts, ?) - MAX(start_ts, ?)) AS seconds
               FROM activity
               WHERE end_ts > ? AND start_ts < ?
                 AND chrome_url IS NOT NULL AND chrome_url != ''
               GROUP BY chrome_url
               ORDER BY seconds DESC
               LIMIT ?""",
            (end_ts, start_ts, start_ts, end_ts, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def hourly_breakdown(start_ts: int, end_ts: int) -> dict:
    """Return seconds spent per (hour, category) bucket."""
    intervals = intervals_in_range(start_ts, end_ts)
    # 24 hour buckets
    buckets: dict[int, dict[str, int]] = {h: {} for h in range(24)}
    for iv in intervals:
        s, e = iv["start_ts"], iv["end_ts"]
        cat = iv["category"]
        # split across LOCAL hour boundaries (not UTC) — otherwise timezones
        # with non-integer-hour offsets (e.g. IST = UTC+5:30) misattribute
        # chunks that span a local hour boundary.
        cur = s
        while cur < e:
            lt = time.localtime(cur)
            local_hour = lt.tm_hour
            # seconds from `cur` to the next local hour boundary
            secs_into_hour = lt.tm_min * 60 + lt.tm_sec
            secs_to_next_hour = 3600 - secs_into_hour
            chunk_end = min(e, cur + secs_to_next_hour)
            buckets[local_hour][cat] = buckets[local_hour].get(cat, 0) + (chunk_end - cur)
            cur = chunk_end
    return buckets


def date_range_with_data() -> tuple[str | None, str | None]:
    with cursor() as conn:
        row = conn.execute(
            "SELECT MIN(start_ts) AS mn, MAX(end_ts) AS mx FROM activity"
        ).fetchone()
    if not row or row["mn"] is None:
        return None, None
    return (
        time.strftime("%Y-%m-%d", time.localtime(row["mn"])),
        time.strftime("%Y-%m-%d", time.localtime(row["mx"])),
    )


if __name__ == "__main__":
    init_db()
    print(f"Initialized DB at {DB_PATH}")
