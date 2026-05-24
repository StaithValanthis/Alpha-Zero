"""
chief_daemon.py — Chief of Staff scheduling daemon.
Runs continuously. Spawns agents at their scheduled times (AEST = UTC+10).
Manages the trigger queue and monitors system health.
"""
import os, sys, json, time, requests, threading, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent))
from agent_runner import run_agent, ENV

B = Path(os.path.expanduser("~/btc-agents"))
AEST = ZoneInfo("Australia/Brisbane")

# ── Schedule (AEST) ──────────────────────────────────────────────
DAILY_SCHEDULE = [
    (0,  1,  "daily_reset"),
    (1,  30, "orchestrator"),
    (10, 30, "analysts_parallel"),
    (12, 30, "strategy-tester"),
    (13, 0,  "trader-management"),
    (19, 0,  "reporter"),
]
SUNDAY_ONLY = [
    (20, 0, "journal-agent"),
]

# ── State ─────────────────────────────────────────────────────────
ran_today = set()
last_trigger_check = 0
pipeline_lock = threading.Lock()  # prevents overlapping scheduled tasks
pipeline_lock = threading.Lock()  # prevents overlapping scheduled tasks

def load_json(path, default=None):
    try:
        with open(B / path) as f: return json.load(f)
    except: return default or {}

def write_json(path, data):
    full = B / path
    tmp = str(full) + ".tmp"
    with open(tmp, "w") as f: json.dump(data, f, indent=2)
    os.rename(tmp, str(full))

def discord(title, desc, color=65280):
    wh = ENV.get("DISCORD_WEBHOOK_URL", "")
    if not wh: return
    try:
        requests.post(wh, json={"embeds":[{"title":title,"description":desc,"color":color}]}, timeout=5)
    except: pass

def log_run(agent, status, duration, message):
    syslog = load_json("state/system-log.json", {"entries": []})
    if not isinstance(syslog, dict): syslog = {"entries": []}
    entries = syslog.get("entries", [])
    entries.append({
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": agent,
        "status": status,
        "duration_seconds": duration,
        "notes": message[:300] if message else ""
    })
    syslog["entries"] = entries[-500:]
    write_json("state/system-log.json", syslog)

# ── Daily reset ───────────────────────────────────────────────────
def daily_reset():
    now_aest = datetime.now(AEST)
    today = now_aest.strftime("%Y-%m-%d")
    cold_start_day = load_json("state/system_state.json", {}).get("cold_start_day", 0) + 1

    write_json("state/system_state.json", {
        "computed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cold_start_day": cold_start_day,
        "is_cold_start": cold_start_day <= 14,
        "last_pipeline_completion": None
    })

    scheduled = ["orchestrator","analysts_parallel","strategy-tester","trader-management","reporter"]
    if now_aest.weekday() == 6:
        scheduled.append("journal-agent")

    write_json("state/pipeline_state.json", {
        "date": today,
        "scheduled_today": scheduled,
        "completed_today": [],
        "in_progress": None,
        "failed_today": [],
        "last_update": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    })
    print(f"Daily reset: cold_start_day={cold_start_day}")

# ── Analysts parallel ─────────────────────────────────────────────
def run_analysts_parallel():
    analysts = ["technical-analyst","derivatives-analyst","onchain-macro-analyst","sentiment-news-analyst"]
    results = {}

    def run_one(name):
        r = run_agent(name)
        results[name] = r
        log_run(name, r["status"], r["duration_seconds"], r["message"])

    threads = [threading.Thread(target=run_one, args=(a,)) for a in analysts]
    for t in threads: t.start()

    deadline = time.time() + 1200
    while time.time() < deadline:
        done = [a for a in analysts if (B / "data/analyst_reports" / f"{a.replace('-','_')}.done").exists()]
        if len(done) == 4:
            break
        time.sleep(30)

    for t in threads: t.join(timeout=1)

    done_count = sum(1 for a in analysts if (B/"data/analyst_reports"/f"{a.replace('-','_')}.done").exists())
    print(f"Analysts done: {done_count}/4")

    if done_count < 2:
        discord("Pipeline aborted", f"Only {done_count}/4 analysts completed. Skipping hypothesis pipeline today.", 16711680)
        pipe = load_json("state/pipeline_state.json", {})
        pipe["failed_today"] = pipe.get("failed_today", []) + ["analysts"]
        write_json("state/pipeline_state.json", pipe)
        return False

    if done_count < 4:
        discord("Degraded mode", f"{done_count}/4 analysts completed. Proceeding with available data.", 16776960)

    for step in ["hypothesis-generator", "bull-researcher", "bear-researcher"]:
        r = run_agent(step)
        log_run(step, r["status"], r["duration_seconds"], r["message"])
        time.sleep(5)

    r2_threads = []
    for researcher in ["bull-researcher", "bear-researcher"]:
        t = threading.Thread(target=lambda name=researcher: log_run(
            name + "-r2", *((lambda r: (r["status"], r["duration_seconds"], r["message"]))(run_agent(name, "This is Round 2. Read the opposing researcher's round1 output before responding.")))
        ))
        r2_threads.append(t)
    for t in r2_threads: t.start()
    for t in r2_threads: t.join(timeout=600)

    r = run_agent("synthesis")
    log_run("synthesis", r["status"], r["duration_seconds"], r["message"])
    return True

# ── Trigger queue ─────────────────────────────────────────────────
def process_trigger_queue():
    queue_data = load_json("signals/trigger_queue.json", {"queue": []})
    queue = queue_data.get("queue", [])

    pending = [t for t in queue if t.get("status") == "pending"]
    if not pending:
        return

    trigger = pending[0]
    trigger_id = trigger.get("trigger_id", "unknown")
    print(f"Processing trigger: {trigger_id}")

    for t in queue:
        if t.get("trigger_id") == trigger_id:
            t["status"] = "risk_review"
    write_json("signals/trigger_queue.json", {"queue": queue})

    extra = f"Trigger to evaluate:\n{json.dumps(trigger, indent=2)}"
    r = run_agent("risk-manager", extra)
    log_run("risk-manager", r["status"], r["duration_seconds"], r["message"])

    queue_data = load_json("signals/trigger_queue.json", {"queue": []})
    queue = queue_data.get("queue", [])
    trigger_entry = next((t for t in queue if t.get("trigger_id") == trigger_id), None)
    if not trigger_entry:
        return

    verdict = trigger_entry.get("verdict", "")
    if verdict == "APPROVED":
        trigger_entry["status"] = "executing"
        write_json("signals/trigger_queue.json", {"queue": queue})
        r = run_agent("trader-entry", f"Execute this approved trigger:\n{json.dumps(trigger_entry, indent=2)}")
        log_run("trader-entry", r["status"], r["duration_seconds"], r["message"])
        if r["status"] == "error":
            discord("Trader/Entry failed", f"Trigger {trigger_id}: {r['message']}", 16711680)
    else:
        reason = trigger_entry.get("rejection_reason", "no reason given")
        print(f"Trigger {trigger_id} rejected: {reason}")
        discord("Trigger rejected", f"{trigger_id}: {reason}", 16776960)

# ── Health check ──────────────────────────────────────────────────
def check_health():
    hb = B / "services/position_guardian.heartbeat"
    if hb.exists():
        age = time.time() - hb.stat().st_mtime
        if age > 300:
            discord("Position Guardian stale", f"No heartbeat for {int(age)}s. Restarting...", 16776960)
            subprocess.run("sudo systemctl restart btc-position-guardian", shell=True)

    portfolio = load_json("state/portfolio.json", {})
    if portfolio.get("circuit_breaker_tripped"):
        discord("CIRCUIT BREAKER", "Portfolio circuit breaker is tripped. All trading halted. Manual review required.", 16711680)

# ── Main scheduling loop ──────────────────────────────────────────
def run_scheduled(key):
    pipe = load_json("state/pipeline_state.json", {})
    pipe["in_progress"] = key
    write_json("state/pipeline_state.json", pipe)

    if key == "daily_reset":
        daily_reset()
        result_status = "success"
        duration = 0.0
    elif key == "analysts_parallel":
        ok = run_analysts_parallel()
        result_status = "success" if ok else "partial"
        duration = 0.0
    else:
        r = run_agent(key)
        log_run(key, r["status"], r["duration_seconds"], r["message"])
        result_status = r["status"]
        duration = r["duration_seconds"]
        if r["status"] == "error":
            discord(f"Agent failed: {key}", r["message"][:500], 16711680)

    pipe = load_json("state/pipeline_state.json", {})
    pipe["in_progress"] = None
    completed = pipe.get("completed_today", [])
    completed.append(key)
    pipe["completed_today"] = completed
    pipe["last_update"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_json("state/pipeline_state.json", pipe)
        print(f"Scheduled task complete: {key} ({result_status})")
    finally:
        pipeline_lock.release()


print("=" * 50)
print(" BTC Agent System — Chief of Staff Daemon")
print(f" Started: {datetime.now(AEST).strftime('%Y-%m-%d %H:%M AEST')}")
print("=" * 50)

discord("Chief of Staff started", f"Daemon online at {datetime.now(AEST).strftime('%H:%M AEST')}. First Orchestrator run at 01:30 AEST.", 65280)

while True:
    try:
        now_aest = datetime.now(AEST)
        h, m = now_aest.hour, now_aest.minute
        today_key = now_aest.strftime("%Y-%m-%d")
        is_sunday = now_aest.weekday() == 6

        schedule = DAILY_SCHEDULE + (SUNDAY_ONLY if is_sunday else [])
        for sched_h, sched_m, task_key in schedule:
            window_key = f"{today_key}_{task_key}"
            if h == sched_h and m == sched_m and window_key not in ran_today:
                ran_today.add(window_key)
                print(f"\n[{now_aest.strftime('%H:%M')}] Scheduled: {task_key}")
                threading.Thread(target=run_scheduled, args=(task_key,), daemon=True).start()

        if h == 0 and m == 0:
            ran_today = {k for k in ran_today if k.startswith(today_key)}

        if time.time() - last_trigger_check > 300:
            last_trigger_check = time.time()
            threading.Thread(target=process_trigger_queue, daemon=True).start()
            check_health()

    except Exception as e:
        print(f"Chief loop error: {e}")
        discord("Chief daemon error", str(e)[:400], 16711680)

    time.sleep(60)
