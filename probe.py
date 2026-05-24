"""One-shot diagnostic. Run it while Chrome is frontmost:

  ./.venv/bin/python probe.py

Prints exactly what the collector sees, plus an independent Chrome AppleScript call.
"""
from __future__ import annotations

import json
import subprocess
import time

from collector import take_sample, _CHROME_SCRIPT, get_frontmost_app, get_window_title

print("=== sample 1 (immediate) ===")
s = take_sample()
print(json.dumps(s.__dict__, indent=2, default=str))

print("\n=== independent Chrome AppleScript probe ===")
out = subprocess.run(
    ["osascript", "-e", _CHROME_SCRIPT],
    capture_output=True, text=True, timeout=4,
)
print("stdout:", repr(out.stdout))
print("stderr:", repr(out.stderr))
print("returncode:", out.returncode)

print("\n=== waiting 3s, then sample again ===")
time.sleep(3)
print("Frontmost now:", get_frontmost_app())
s = take_sample()
print(json.dumps(s.__dict__, indent=2, default=str))
