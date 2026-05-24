# OnChain/Macro Analyst
# Model: coordinator (Haiku 4.5) | Schedule: daily 10:30 AEST (parallel)

## Inputs
- data/onchain/mempool.json
- data/onchain/blockchair.json
- data/macro/fear_greed_7d.json
- data/macro/btc_market.json

## Output: data/analyst_reports/onchain_macro_analyst.json
Then: data/analyst_reports/onchain_macro_analyst.done

## Required findings fields
{
  "schema_version": "1.0",
  "agent": "onchain_macro_analyst",
  "produced_at": "...",
  "stale_after_seconds": 7200,
  "findings": {
    "fear_greed_current": 0,
    "fear_greed_7d_values": [],
    "fear_greed_trend": "improving | deteriorating | stable",
    "fear_greed_signal": "extreme_fear_buy_signal | fear | neutral | greed | extreme_greed_caution",
    "mempool_congestion": "low | moderate | high",
    "mempool_fee_fast_sat_vb": 0,
    "network_health": "1 sentence on transaction activity and any anomalies",
    "btc_24h_change_pct": 0.0,
    "btc_market_cap_usd": 0,
    "accumulation_signal": "strong | moderate | neutral | distribution",
    "top_onchain_signal": "the single most significant observation"
  }
}

Write .done file LAST.
