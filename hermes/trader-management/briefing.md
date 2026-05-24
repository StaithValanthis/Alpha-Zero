# Trader/Management
# Model: coordinator (Haiku 4.5) | Schedule: daily 13:00 AEST

## Task 1: Duration review
For each open position: check entry_date + max_duration_days vs today.
If expired: write close instruction to state/orchestrator-strategy-actions.json.
If >80% elapsed: flag approaching_expiry in system-log.json.

## Task 2: Correlation check
≥2 open positions: estimate pairwise correlation from data/historical/.
Any pair > 0.90 → URGENT Discord. avg > 0.75 → log warning.

## Task 3: Balance reconciliation (READ-ONLY Bybit key)
GET https://api.bybit.com/v5/account/wallet-balance?accountType=UNIFIED
Use BYBIT_READONLY_API_KEY. Compare to portfolio.json.
Divergence > 0.5% → flag + WARNING Discord.

## Task 4: Execution quality update
Rolling 30-trade avg slippage. Update portfolio.json execution_quality.
> 0.15% → flag "high slippage" in system-log.json.

## Task 5: Stale signal cleanup
Remove signals where entry condition is obviously no longer valid.

## Task 6: Consecutive loss circuit check
Any strategy at count ≥ 3 not yet suspended → add to system-log.json, notify Chief.

## Files you may write
- state/portfolio.json (execution_quality only, with portfolio.lock)
- state/signals.json (cleanup only)
- state/system-log.json (append entries)
- state/orchestrator-strategy-actions.json (close instructions)

## Commit
git add state/portfolio.json state/signals.json state/system-log.json
git commit -m "trader-management: maintenance $(date -u +%Y-%m-%d)"
git push origin HEAD:main
