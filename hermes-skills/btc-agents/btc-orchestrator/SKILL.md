---
name: btc-orchestrator
description: Daily strategic director for BTC accumulation system. Reads all state, writes orchestrator-directive.json, Sunday full audit and weekly-review.
triggers:
  - cron: "30 15 * * *"
---

## Task

You are a delegated subagent running as the BTC Orchestrator. Your role is strategic direction for an autonomous BTC accumulation system.

**Read your briefing first**: `hermes/orchestrator/briefing.md` — follow it completely.

### Inputs to read before any decision
- `state/portfolio.json`
- `state/strategies.json`
- `state/research.json`
- `state/lessons.json`
- `state/system-log.json`
- `state/pipeline_state.json`
- `state/anomaly_state.json`
- `state/system_state.json`
- `hermes/orchestrator/memory/feedback.jsonl` (if exists)

### Derive cold_start_day directly
Do NOT read cold_start_day from system_state.json for decisions. Derive it yourself:
```python
from datetime import date, timezone, datetime
import json
portfolio = json.load(open("state/portfolio.json"))
starting = date.fromisoformat(portfolio["starting_date"])
cold_start_day = (datetime.now(timezone.utc).date() - starting).days
```

### Execute briefing
Follow all steps in hermes/orchestrator/briefing.md.

### Sunday additions
If today is Sunday AEST:
- Write `state/weekly-review.json`
- Write `state/orchestrator-strategy-actions.json` with `retire` and `promote` lists
- Write targeted feedback to each agent memory directory:
  - `hermes/strategy-tester/memory/feedback.jsonl`
  - `hermes/bull-researcher/memory/feedback.jsonl`
  - `hermes/bear-researcher/memory/feedback.jsonl`
  - `hermes/trader-entry/memory/feedback.jsonl`

### Commit and push
```bash
git add state/orchestrator-directive.json state/lessons.json
# Sunday: also add state/weekly-review.json state/orchestrator-strategy-actions.json
git commit -m "orchestrator: directive $(date -u +%Y-%m-%d)"
git push origin HEAD:main
```

### Discord notification
Post completion embed to `$DISCORD_WEBHOOK_URL` with title "Orchestrator Complete", fields: cold_start_day, directive summary, focus areas, any strategy suspensions.
