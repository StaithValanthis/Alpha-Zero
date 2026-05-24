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

### Commit
```bash
git add state/portfolio.json
git commit -m "trader-management: daily check $(date -u +%Y-%m-%d)"
git push origin HEAD:main
```
