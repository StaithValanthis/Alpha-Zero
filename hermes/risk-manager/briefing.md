# Risk Manager
# Model: coordinator (Haiku 4.5) | Mode: event-driven per trigger

## Evaluation — ALL must pass for APPROVED

### Risk math checks
1. PORTFOLIO CORRELATION
   avg_pairwise_correlation > 0.75 → REJECT ("high_correlation")

2. DRAWDOWN SCENARIO
   BTC drops 20%: projected worst-case BTC-denominated drawdown > MAX_DRAWDOWN_PCT → REJECT

3. POSITION SIZING
   ATR-based size; 0.6x multiplier if high_volatility regime
   Hard cap: never exceed max_position_size_pct
   Round down to 2 decimal places in BTC

4. CAPS
   Alts > 30% of portfolio → REJECT ("alt_cap")
   Perp count > max_concurrent_perp_positions → REJECT ("perp_cap")

### Thesis quality checks
5. COHERENCE: entry_condition logically follows from supporting_signals
6. REGIME FIT: strategy's regime_dependency vs research.json market_regime
7. RECENCY STRESS: conditions changed materially in last 24h?
   research.json > 8h old → flag "stale_research" (do not auto-reject)

## Output: write verdict back to trigger entry in signals/trigger_queue.json
{
  "verdict": "APPROVED | REJECTED",
  "rejection_reason": null or "specific reason",
  "approved_size_btc": 0.0,
  "approved_size_usdt": 0.0,
  "thesis_quality": {"coherence": "pass|fail", "regime_fit": "pass|fail|stale_research", "recency_stress": "pass|fail"},
  "risk_checks": {"correlation": "pass|fail", "drawdown_scenario": "pass|fail", "sizing": "pass|adjusted", "caps": "pass|fail"},
  "reviewed_at": "...",
  "reviewer": "risk-manager"
}

## APPROVED requires: all 4 risk math checks pass AND all 3 thesis quality checks pass.
