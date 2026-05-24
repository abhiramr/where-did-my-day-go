"""Flask dashboard server.

Routes:
  GET /                         -> dashboard HTML
  GET /api/summary?date=YYYY-MM-DD   -> totals, idle, top apps, urls, hourly
  GET /api/timeline?date=YYYY-MM-DD  -> list of intervals for the day
  GET /api/range                -> earliest/latest day with data
"""
from __future__ import annotations

import time

from flask import Flask, jsonify, render_template, request

import db


app = Flask(__name__, static_folder="static", template_folder="templates")


def _today_str() -> str:
    return time.strftime("%Y-%m-%d", time.localtime())


def _parse_date(s: str | None) -> str:
    if not s:
        return _today_str()
    try:
        time.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return _today_str()


@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/api/range")
def api_range():
    earliest, latest = db.date_range_with_data()
    return jsonify({"earliest": earliest, "latest": latest, "today": _today_str()})


@app.route("/api/summary")
def api_summary():
    date = _parse_date(request.args.get("date"))
    start, end = db.day_bounds(date)
    now = int(time.time())
    # don't count future seconds
    effective_end = min(end, now) if date == _today_str() else end

    categories = db.totals_by_category(start, effective_end)
    apps = db.totals_by_app(start, effective_end)
    urls = db.top_chrome_urls(start, effective_end)
    hourly = db.hourly_breakdown(start, effective_end)

    cat_map = {c["category"]: c["seconds"] for c in categories}
    active_seconds = sum(s for c, s in cat_map.items() if c != "idle")
    idle_seconds = cat_map.get("idle", 0)
    tracked_seconds = active_seconds + idle_seconds

    return jsonify({
        "date": date,
        "start_ts": start,
        "end_ts": effective_end,
        "tracked_seconds": tracked_seconds,
        "active_seconds": active_seconds,
        "idle_seconds": idle_seconds,
        "categories": categories,
        "apps": apps,
        "urls": urls,
        "hourly": hourly,
    })


@app.route("/api/probe")
def api_probe():
    """Run one live sample + an independent Chrome AppleScript call.
    Hit this from your browser while Chrome is frontmost to debug detection.
    """
    import subprocess
    from collector import take_sample, _CHROME_SCRIPT

    s = take_sample()
    out = subprocess.run(
        ["osascript", "-e", _CHROME_SCRIPT],
        capture_output=True, text=True, timeout=4,
    )
    return jsonify({
        "sample": s.__dict__,
        "chrome_script_stdout": out.stdout,
        "chrome_script_stderr": out.stderr,
        "chrome_script_returncode": out.returncode,
    })


@app.route("/api/timeline")
def api_timeline():
    date = _parse_date(request.args.get("date"))
    start, end = db.day_bounds(date)
    now = int(time.time())
    effective_end = min(end, now) if date == _today_str() else end
    intervals = db.intervals_in_range(start, effective_end)
    return jsonify({
        "date": date,
        "start_ts": start,
        "end_ts": effective_end,
        "intervals": intervals,
    })


if __name__ == "__main__":
    import os
    db.init_db()
    port = int(os.environ.get("PORT", 5173))
    app.run(host="127.0.0.1", port=port, debug=False)
