---
name: intraday-risk-watchdog
description: No-LLM daemon that monitors ws_prices.json for flash crash (>=5% drop in one 5-min tick), funding rate inversion (extreme negative < -0.03%), and stablecoin depeg proxy (btc_market price divergence vs internal baseline). On trigger: sets anomaly_state.json.auto_pause_signal_watcher=true, posts an urgent Discord embed, writes an entry to state/system-log.json. Resets auto_pause only when price recovers threshold AND 30 min have elapsed.

triggers:
  - cron: "*/5 * * * *"
---

## Task

You are a delegated subagent running as the Intraday Risk Watchdog.

**Read your briefing first**: `hermes/intraday-risk-watchdog/briefing.md` — follow it completely.

### Inputs
Read:
- `data/market/ws_prices.json`
- `data/market/funding_history.json`

### Step 1: Write report
Follow the exact schema in your briefing.

### Step 2: Commit
```bash
git add state/anomaly_state.json (auto_pause_signal_watcher field) state/system-log.json (append on trigger) Discord webhook (urgent embed on trigger only)
git commit -m "intraday-risk-watchdog: daily report $(date -u +%Y-%m-%d)"
git push origin HEAD:main
```

### Tone
Factual. Lead with numbers. Be specific.
