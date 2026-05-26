---
name: btc-strategy-tester
description: Daily strategy backtester and signal generator. Runs after morning pipeline. Updates strategies.json and generates signals.json.
triggers:
  - cron: "30 2 * * *"
---

## Task

You are a delegated subagent running as the BTC Strategy Tester. Run after the morning pipeline has completed.

**Read your briefing first**: `hermes/strategy-tester/briefing.md` — follow it completely.

### Inputs
- `state/research.json` (today's regime and approved hypotheses)
- `state/strategies.json` (all 18 strategies — many are legacy with entry_condition string format)
- `state/orchestrator-directive.json`
- `state/orchestrator-strategy-actions.json` (apply retire/promote actions from Sunday)
- `hermes/strategy-tester/memory/feedback.jsonl` (if exists)

### Legacy strategy migration
Check all strategies for missing `watcher_compatible` field — these are legacy strategies from the old architecture:
- For each strategy without `watcher_compatible`: evaluate if `entry_condition` string can be translated to a structured `entry_conditions` array
- If translatable: translate it, set `watcher_compatible: true`
- If not translatable: set `watcher_compatible: false` with a `migration_note` explaining why
- This migration is progressive — don't fail if some strategies can't be migrated yet

### Run backtests
```bash
python3 tools/backtester.py
```
Follow briefing for interpreting results and updating strategy scores.

### Generate signals
Based on current regime and strategy performance, write `state/signals.json` with any actionable signals.

### Thesis validity
Follow briefing for any thesis validity checks that are due.

### Apply orchestrator strategy actions
From `state/orchestrator-strategy-actions.json`:
- `retire` list: set strategy status to "retired" with retire_date
- `promote` list: update strategy status per briefing guidelines


### Update pipeline completion tracking
```python
import json, os
from datetime import datetime, timezone
ps_path = "state/pipeline_state.json"
with open(ps_path) as f: ps = json.load(f)
if "strategy-tester" not in ps.get("completed_today", []):
    ps.setdefault("completed_today", []).append("strategy-tester")
ps["last_update"] = datetime.now(timezone.utc).isoformat()
tmp = ps_path + ".tmp"
with open(tmp, "w") as f: json.dump(ps, f, indent=2)
os.replace(tmp, ps_path)
```
### Commit
```bash
git add state/strategies.json state/signals.json state/lessons.json
git commit -m "strategy-tester: daily run $(date -u +%Y-%m-%d)"
git push origin HEAD:main
```

### Lessons writes
Use tools/_state_utils.append_lessons() — NEVER overwrite lessons.json.
See hermes/strategy-tester/briefing.md "Lessons write rule" section for full schema.
