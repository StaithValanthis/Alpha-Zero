---
name: intraday-risk-watchdog
description: No-LLM daemon that monitors ws_prices.json for flash crash (>=5% drop in one 5-min tick), funding rate inversion (extreme negative < -0.03%), and stablecoin depeg proxy (btc_market price divergence vs internal baseline). On trigger: sets anomaly_state.json.auto_pause_signal_watcher=true, posts an urgent Discord embed, writes an entry to state/system-log.json. Resets auto_pause only when price recovers threshold AND 30 min have elapsed.

triggers:
  - cron: "*/5 * * * *"
---

## Task

This is a **no-LLM watchdog**. The Hermes cron runs `services/intraday_risk_watchdog.py` directly via `no_agent=True`. There is no LLM agent loop.

If you are reading this as a delegated subagent, the cron is misconfigured. The correct registration uses `--script services/intraday_risk_watchdog.py --no-agent`. Do not attempt to run this as an LLM task.

### What the script does
- Reads `data/market/ws_prices.json` and `data/market/funding_history.json`
- Triggers on: 5-min price drop >= 5%, 1-hr drop >= 8%, or funding_rate < -0.03%
- On trigger: writes `state/anomaly_state.json` (auto_pause_signal_watcher=true), appends `state/system-log.json`, POSTs Discord alert
- Clears auto_pause after 30 min hold once trigger conditions resolve
- Silent on clean runs (empty stdout = no delivery)
