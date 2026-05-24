---
name: btc-trigger-queue
description: Every-5-min trigger queue processor — bridges live_triggers to queue, runs safety checks, delegates Risk Manager and Trader/Entry.
triggers:
  - cron: "*/5 * * * *"
---

## Task

You are a delegated subagent processing the BTC trigger queue. This runs every 5 minutes.

### Stage 0: Concurrency lock

Check `signals/trigger_queue.lock`:
- If file exists AND is less than 15 minutes old: **exit immediately** — another session is running.
- If file exists AND is older than 15 minutes: delete it (stale from crashed session), then continue.

Write the lock file before proceeding:
```json
{"locked_at": "<UTC ISO>", "pid": "<session_id>"}
```

**Use try/finally** — remove `signals/trigger_queue.lock` at the end regardless of success or failure.

### Stage 1: Bridge live_triggers → trigger_queue

Read `signals/live_triggers.json`. For each trigger:
- If its `trigger_id` is NOT already in `signals/trigger_queue.json`: add it with `status: "pending"`
Write `signals/trigger_queue.json` atomically (write to .tmp then rename).

### Stage 1b: Recover stale risk_review entries

For each entry in trigger_queue.json with `status: "risk_review"`:
- Check `locked_at` or `fired_at` timestamp
- If older than 15 minutes: reset status to `"pending"` (previous session crashed)

### Stage 2: Safety checks

Read the following and stop (remove lock, exit) if any of these are true:
- `state/portfolio.json` → `circuit_breaker_tripped: true`
- `state/orchestrator-directive.json` → `signal_watcher_paused: true`
- `state/anomaly_state.json` → `auto_pause_signal_watcher: true`

### Stage 3a: Process portfolio_guardian_pending.json

Read `state/portfolio_guardian_pending.json`. If it has `pending_actions` AND `state/portfolio.lock` does NOT exist:

1. Write `state/portfolio.lock`: `{"locked_by": "trigger-queue-guardian", "locked_at": "<UTC ISO>"}`
2. For each action (stop hit / TP hit):
   - Update `state/portfolio.json`: close the position, record actual exit price, calculate BTC P&L, move from open_positions to closed_trades
3. Clear `state/portfolio_guardian_pending.json`
4. Delete `state/portfolio.lock`
5. Append entry to `state/system-log.json`
6. Post Discord embed with position close details

**Always delete portfolio.lock in a finally block.**

### Stage 3b: Process one pending trigger

Find the first entry in `signals/trigger_queue.json` with `status: "pending"`.

1. Set its status to `"risk_review"`, write atomically.
2. Delegate Risk Manager:
   - Read `hermes/risk-manager/briefing.md`
   - Evaluate the trigger
   - Write verdict back to the trigger entry in `signals/trigger_queue.json`

3. If verdict is `"APPROVED"`:
   - Delegate Trader/Entry:
     - Read `hermes/trader-entry/briefing.md`
     - Acquire `state/portfolio.lock`
     - Place order on Bybit
     - Update `state/portfolio.json`
     - Release lock

4. If verdict is `"REJECTED"`:
   - Update trigger status to `"rejected"` in queue
   - Append to `state/system-log.json`
   - If rejection_reason is urgent (circuit breaker, drawdown limit): post to Discord

### Finally
Remove `signals/trigger_queue.lock`.
