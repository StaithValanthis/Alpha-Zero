#!/usr/bin/env python3
"""
chief_triage.py — Daily Chief of Staff system health triage.
No LLM. Runs at 19:30 UTC (05:30 AEST) — after reporter, before next orchestrator.

Reads:
  - logs/hermes-gateway.log      (job failures)
  - logs/llm_router.log          (LLM routing health)
  - data/meta/collection_status.json  (collector freshness)
  - data/analyst_reports/*.json  (analyst freshness)
  - state/pipeline_state.json    (pipeline completion)
  - proposals/pending/*.yaml     (pending proposal age)
  - services/position_guardian.heartbeat  (guardian liveness)
  - state/portfolio.json         (circuit breaker, open positions)
  - state/anomaly_state.json     (active anomalies)

Outputs:
  - state/chief_triage.json      (structured findings, always written)
  - Discord embed                (only if severity >= WARNING)
  - Prints issues to stdout      (for Hermes delivery if non-empty)

Silent on fully healthy days. Escalates same-day on actionable issues.
"""

import json
import os
import re
import time
import glob
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import requests

B = os.path.expanduser("~/btc-agents")
NOW = datetime.now(tz=timezone.utc)
TODAY_STR = NOW.strftime("%Y-%m-%d")
LOOKBACK_H = 25  # scan last 25h of gateway log


# ── Helpers ──────────────────────────────────────────────────────────────────

def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def load_env():
    env = {}
    try:
        with open(f"{B}/.env") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def age_h(path):
    """Hours since file was last modified. None if missing."""
    try:
        return (time.time() - os.path.getmtime(path)) / 3600
    except Exception:
        return None


def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ── 1. Gateway log — job failures in last 25h ────────────────────────────────

def parse_gateway_failures():
    """Return {job_name: [error_msg, ...]} for failures in lookback window.
    
    Gateway log has no per-line timestamps. We use line position as a proxy
    for recency — only scan the last N lines. Tune LOOKBACK_LINES to roughly
    match the lookback window given current log volume.
    """
    log_path = f"{B}/logs/hermes-gateway.log"
    LOOKBACK_LINES = 800  # approx last 2-3h of activity at typical volume
    failures = defaultdict(list)

    job_fail_pat = re.compile(r"Job '([^']+)' failed: RuntimeError: (.+)")

    try:
        with open(log_path) as f:
            lines = f.readlines()
    except Exception:
        return {}, {}

    recent_lines = lines[-LOOKBACK_LINES:]

    for line in recent_lines:
        m = job_fail_pat.search(line)
        if m:
            job, err = m.group(1), m.group(2)[:120]
            failures[job].append(err)

    return dict(failures), {}


# ── 2. LLM routing health from daily_usage ───────────────────────────────────

def parse_routing_health():
    issues = []
    usage_path = f"{B}/logs/daily_usage/{TODAY_STR}.json"
    usage = load(usage_path, {})
    if not usage:
        # Try yesterday
        yesterday = (NOW - timedelta(days=1)).strftime("%Y-%m-%d")
        usage = load(f"{B}/logs/daily_usage/{yesterday}.json", {})

    alerts = usage.get("alerts", [])
    for a in alerts:
        issues.append(a)

    # Check if any tier has 0% hit rate
    for tier, stats in usage.get("by_tier", {}).items():
        if stats.get("calls", 0) > 0 and stats.get("primary_hit_rate_pct", 100) == 0:
            issues.append(f"TIER {tier}: 0% primary hit rate ({stats['calls']} calls) — provider unreachable")

    return issues


# ── 3. Collection status ──────────────────────────────────────────────────────

def check_collection():
    issues = []
    status = load(f"{B}/data/meta/collection_status.json", {})
    collectors = status.get("collectors", {})
    checked_at = status.get("checked_at", "")

    # If collection_status itself is stale, that's a problem
    cs_age = age_h(f"{B}/data/meta/collection_status.json")
    if cs_age is not None and cs_age > 2:
        issues.append(f"collection_status.json is {cs_age:.1f}h stale — collection_monitor may be down")

    for name, info in collectors.items():
        health = info.get("health", "unknown")
        age_s = info.get("age_seconds", 0)
        if health == "red":
            issues.append(f"COLLECTOR RED: {name} — {age_s//3600:.0f}h {(age_s%3600)//60:.0f}m stale")

    return issues


# ── 4. Analyst report freshness ───────────────────────────────────────────────

def check_analysts():
    issues = []
    expected = [
        "technical_analyst", "derivatives_analyst",
        "onchain_macro_analyst", "sentiment_news_analyst"
    ]
    for name in expected:
        path = f"{B}/data/analyst_reports/{name}.json"
        a = age_h(path)
        if a is None:
            issues.append(f"ANALYST MISSING: {name}.json — never written")
        elif a > 26:
            issues.append(f"ANALYST STALE: {name}.json — {a:.0f}h old (pipeline may not have run)")

    # Options analyst — tolerate up to 26h (runs at 23:45 UTC)
    opts_age = age_h(f"{B}/data/analyst_reports/options_analyst.json")
    if opts_age is not None and opts_age > 26:
        issues.append(f"ANALYST STALE: options_analyst.json — {opts_age:.0f}h old")

    return issues


# ── 5. Pipeline completion ────────────────────────────────────────────────────

def check_pipeline():
    issues = []
    ps = load(f"{B}/state/pipeline_state.json", {})
    date = ps.get("date", "")
    completed = ps.get("completed_today", [])
    failed = ps.get("failed_today", [])

    if date != TODAY_STR:
        issues.append(f"pipeline_state.json date={date} — daily_reset may not have run today")

    if failed:
        issues.append(f"PIPELINE FAILED: {', '.join(failed)}")

    return issues


# ── 6. Pending proposals ──────────────────────────────────────────────────────

def check_proposals():
    issues = []
    pending = glob.glob(f"{B}/proposals/pending/*.yaml")
    old_pending = []
    for p in pending:
        a = age_h(p)
        if a is not None and a > 48:
            old_pending.append((os.path.basename(p), a))

    if old_pending:
        names = ", ".join(f"{n} ({a:.0f}h)" for n, a in old_pending)
        issues.append(f"PROPOSALS AWAITING REVIEW ({len(old_pending)}): {names}")

    return issues, len(pending)


# ── 7. Position guardian liveness ────────────────────────────────────────────

def check_guardian():
    issues = []
    hb_path = f"{B}/services/position_guardian.heartbeat"
    a = age_h(hb_path)
    if a is None:
        issues.append("GUARDIAN: heartbeat file missing — position_guardian.py may not be running")
    elif a > 0.25:  # >15 min stale
        issues.append(f"GUARDIAN: heartbeat {a*60:.0f}min stale — may have crashed")
    return issues


# ── 8. Portfolio safety ───────────────────────────────────────────────────────

def check_portfolio():
    issues = []
    portfolio = load(f"{B}/state/portfolio.json", {})

    if portfolio.get("circuit_breaker_tripped"):
        issues.append("CIRCUIT BREAKER TRIPPED — all trading halted, manual review required")

    anomaly = load(f"{B}/state/anomaly_state.json", {})
    if anomaly.get("auto_pause_signal_watcher"):
        active = anomaly.get("current_anomalies", [])
        types = [a.get("type", "?") for a in active]
        issues.append(f"SIGNAL WATCHER PAUSED: {', '.join(types) or 'unknown trigger'}")

    return issues


# ── Severity classification ───────────────────────────────────────────────────

def classify(job_failures, routing_issues, collection_issues,
             analyst_issues, pipeline_issues, proposal_issues, guardian_issues, portfolio_issues):
    """Return (severity, all_issues_list)"""
    all_issues = []

    # Portfolio safety is always CRITICAL
    for i in portfolio_issues:
        all_issues.append(("CRITICAL", i))

    # Job failures: >=5 failures on a core pipeline job = CRITICAL; 1-4 = WARNING
    core_jobs = {
        "btc-orchestrator-daily", "btc-morning-pipeline",
        "btc-strategy-tester-daily", "btc-trader-management-daily",
        "btc-reporter-daily", "btc-trigger-queue-check"
    }
    for job, errs in job_failures.items():
        count = len(errs)
        most_common = Counter(errs).most_common(1)[0][0] if errs else "unknown"
        if job in core_jobs:
            sev = "CRITICAL" if count >= 5 else "WARNING"
        else:
            sev = "WARNING" if count >= 3 else "INFO"
        all_issues.append((sev, f"JOB {job}: {count} failure(s) — {most_common[:80]}"))

    for i in collection_issues:
        all_issues.append(("WARNING", i))
    for i in analyst_issues:
        all_issues.append(("WARNING", i))
    for i in pipeline_issues:
        all_issues.append(("WARNING", i))
    for i in routing_issues:
        all_issues.append(("INFO", i))
    for i in proposal_issues:
        all_issues.append(("INFO", i))
    for i in guardian_issues:
        all_issues.append(("WARNING", i))

    if not all_issues:
        return "OK", []

    severities = [s for s, _ in all_issues]
    if "CRITICAL" in severities:
        return "CRITICAL", all_issues
    if "WARNING" in severities:
        return "WARNING", all_issues
    return "INFO", all_issues


# ── Discord post ──────────────────────────────────────────────────────────────

def post_discord(env, severity, issues, pending_count, cold_start_day):
    webhook = env.get("DISCORD_WEBHOOK_URL", "")
    if not webhook:
        return

    color_map = {"CRITICAL": 15158332, "WARNING": 16776960, "INFO": 3447003, "OK": 65280}
    color = color_map.get(severity, 3447003)

    lines = []
    for sev, msg in sorted(issues, key=lambda x: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(x[0], 3)):
        icon = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🔵"}.get(sev, "⚪")
        lines.append(f"{icon} {msg}")

    description = "\n".join(lines[:15])  # cap at 15 items
    if len(issues) > 15:
        description += f"\n... and {len(issues) - 15} more"

    embed = {
        "title": f"Chief Triage — {severity} — {NOW.strftime('%Y-%m-%d %H:%M UTC')}",
        "description": description,
        "color": color,
        "footer": {"text": f"Cold start day {cold_start_day} | {pending_count} proposal(s) pending | $0.00"}
    }

    try:
        requests.post(webhook, json={"embeds": [embed]}, timeout=5)
    except Exception as e:
        print(f"Discord post failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    env = load_env()

    # Compute cold_start_day
    portfolio = load(f"{B}/state/portfolio.json", {})
    cold_start_day = 0
    try:
        from datetime import date
        starting = date.fromisoformat(portfolio.get("starting_date", TODAY_STR))
        cold_start_day = (NOW.date() - starting).days
    except Exception:
        pass

    # Run all checks
    job_failures, _ = parse_gateway_failures()
    routing_issues = parse_routing_health()
    collection_issues = check_collection()
    analyst_issues = check_analysts()
    pipeline_issues = check_pipeline()
    proposal_issues_list, pending_count = check_proposals()
    guardian_issues = check_guardian()
    portfolio_issues = check_portfolio()

    severity, all_issues = classify(
        job_failures, routing_issues, collection_issues,
        analyst_issues, pipeline_issues, proposal_issues_list,
        guardian_issues, portfolio_issues
    )

    # Write triage state
    triage = {
        "produced_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "severity": severity,
        "cold_start_day": cold_start_day,
        "pending_proposals": pending_count,
        "issue_count": len(all_issues),
        "issues": [{"severity": s, "message": m} for s, m in all_issues],
        "job_failure_counts": {k: len(v) for k, v in job_failures.items()},
    }
    atomic_write(f"{B}/state/chief_triage.json", triage)

    if severity == "OK":
        # Silent — no stdout, no Discord
        return

    # Print summary to stdout (delivered by Hermes on non-empty)
    print(f"Chief Triage [{severity}] — {NOW.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"Cold start day {cold_start_day} | {pending_count} pending proposal(s)")
    print()
    for sev, msg in sorted(all_issues, key=lambda x: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}.get(x[0], 3)):
        print(f"[{sev}] {msg}")

    # Post Discord for WARNING+
    if severity in ("CRITICAL", "WARNING"):
        post_discord(env, severity, all_issues, pending_count, cold_start_day)


if __name__ == "__main__":
    main()
