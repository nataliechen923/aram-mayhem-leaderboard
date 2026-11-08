#!/usr/bin/env python3
"""Freshness gate for the daily leaderboard update.

Runs after the updater in GitHub Actions. Exits non-zero (which makes the
workflow fail, and GitHub emails the repo owner) only when BOTH are true:
the leaderboard data is stale AND the last update attempt recorded an
error — i.e. the automation itself is broken and a human needs to look.
It stays quiet before setup is done (no update attempt recorded yet),
when the data is fresh, and when the updater is keeping a good snapshot
while PlayARAM is temporarily unreachable, so it never nags.

Usage: python3 scripts/check_fresh.py [max_age_hours]
Default max age: 72 hours (three missed daily runs).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_HOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 72
DATA = Path(__file__).resolve().parent.parent / "data" / "data.json"

data = json.loads(DATA.read_text())
meta = data.get("meta", {})
automation = meta.get("automation", {})

if not automation.get("last_attempt"):
    print("check_fresh: no update attempt recorded yet — setup not done, skipping gate.")
    sys.exit(0)

updated = meta.get("updated_at")
if not updated:
    age_hours = float("inf")
else:
    updated_dt = datetime.fromisoformat(updated)
    if updated_dt.tzinfo is None:
        updated_dt = updated_dt.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600

print(f"check_fresh: data age {age_hours:.1f}h (limit {MAX_HOURS}h), "
      f"last attempt {automation.get('last_attempt_label')}, "
      f"last error: {automation.get('last_error')}")
if age_hours > MAX_HOURS and automation.get("last_error"):
    print("check_fresh: STALE + last attempt errored — the daily update "
          f"has not succeeded in {MAX_HOURS}h. "
          f"Last error: {automation.get('last_error')}")
    sys.exit(1)
print("check_fresh: fresh enough, or no error recorded.")
sys.exit(0)
