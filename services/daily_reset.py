#!/usr/bin/env python3
"""Daily midnight reset — runs at 00:01 AEST (14:01 UTC). No LLM calls."""

import json
import os
import glob
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

BASE = "/home/btc-agent/btc-agents"
STATE = f"{BASE}/state"
DATA = f"{BASE}/data"
AEST = ZoneInfo("Australia/Brisbane")


def load_json(path):
    with open(path) as f:
        return json.load(f)


def write_json(path, obj):
    with open(path + ".tmp", "w") as f:
        json.dump(obj, f, indent=2)
    os.replace(path + ".tmp", path)


def compute_cold_start_day():
    portfolio = load_json(f"{STATE}/portfolio.json")
    starting_date_str = portfolio.get("starting_date", "")
    if not starting_date_str:
        return 0, True
    starting_date = date.fromisoformat(starting_date_str)
    today_utc = datetime.now(timezone.utc).date()
    cold_start_day = (today_utc - starting_date).days
    return cold_start_day, cold_start_day < 14


def reset_system_state(cold_start_day, is_cold_start):
    obj = {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "cold_start_day": cold_start_day,
        "is_cold_start": is_cold_start,
        "btc_price_usdt": 0,
        "last_pipeline_completion": None,
    }
    write_json(f"{STATE}/system_state.json", obj)
    print(f"  system_state.json: cold_start_day={cold_start_day}, is_cold_start={is_cold_start}")


def reset_pipeline_state():
    now_aest = datetime.now(AEST)
    today_aest = now_aest.date()
    is_sunday = now_aest.weekday() == 6  # Sunday in AEST calendar day

    scheduled = [
        "orchestrator",
        "morning-pipeline",
        "strategy-tester",
        "trader-management",
        "reporter",
    ]
    if is_sunday:
        scheduled.append("journal-agent")

    obj = {
        "date": today_aest.isoformat(),
        "scheduled_today": scheduled,
        "completed_today": [],
        "in_progress": None,
        "failed_today": [],
        "last_update": datetime.now(timezone.utc).isoformat(),
    }
    write_json(f"{STATE}/pipeline_state.json", obj)
    print(f"  pipeline_state.json: date={today_aest}, scheduled={scheduled}")


def delete_stale_done_markers():
    pattern = f"{DATA}/analyst_reports/*.done"
    files = glob.glob(pattern)
    for f in files:
        os.remove(f)
        print(f"  Deleted stale marker: {os.path.basename(f)}")
    if not files:
        print("  No stale .done markers to delete")
    return len(files)


def main():
    print(f"=== Daily Reset @ {datetime.now(AEST).isoformat()} AEST ===")

    print("1. Computing cold_start_day from portfolio.starting_date...")
    cold_start_day, is_cold_start = compute_cold_start_day()
    reset_system_state(cold_start_day, is_cold_start)

    print("2. Resetting pipeline_state.json...")
    reset_pipeline_state()

    print("3. Deleting stale analyst .done markers...")
    deleted = delete_stale_done_markers()

    print(f"=== Reset complete. cold_start_day={cold_start_day}, deleted {deleted} markers ===")


if __name__ == "__main__":
    main()
