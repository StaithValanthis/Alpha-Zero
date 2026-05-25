---
name: btc-trader-management
description: Daily trader management — duration checks, correlation checks, balance reconciliation. Updates portfolio.json.
triggers:
  - cron: "0 3 * * *"
---

## Task

You are a delegated subagent running as the BTC Trader Management agent.

**Read your briefing first**: `hermes/trader-management/briefing.md` — follow it completely.

### Inputs
- `state/portfolio.json`
- `state/strategies.json`

### Execution
Follow all steps in your briefing:
1. Duration checks on open positions
2. Correlation checks across active positions
3. Balance reconciliation with Bybit (read-only API)
4. Any required portfolio adjustments (write via portfolio.lock mechanism)

### Portfolio writes
Always acquire `state/portfolio.lock` before writing `state/portfolio.json`. Write the lock file first, complete the update, then delete the lock. Use a try/finally to ensure lock is always released.


### Update pipeline completion tracking
```python
import json, os
from datetime import datetime, timezone
ps_path = "state/pipeline_state.json"
with open(ps_path) as f: ps = json.load(f)
if "trader-management" not in ps.get("completed_today", []):
    ps.setdefault("completed_today", []).append("trader-management")
ps["last_update"] = datetime.now(timezone.utc).isoformat()
tmp = ps_path + ".tmp"
with open(tmp, "w") as f: json.dump(ps, f, indent=2)
os.replace(tmp, ps_path)
```
### Commit
```bash
git add state/portfolio.json
git commit -m "trader-management: daily check $(date -u +%Y-%m-%d)"
git push origin HEAD:main
```
