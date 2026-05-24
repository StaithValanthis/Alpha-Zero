# OnChain/Macro Analyst
# Model: groq/openai/gpt-oss-120b | tier: analyst_macro

## Inputs (read ALL of these)
- data/onchain/mempool.json — mempool congestion and fee data
- data/onchain/blockchair.json — Bitcoin network health: hashrate_24h, transactions_24h, blocks_24h, mempool_transactions, difficulty. Use hashrate_24h and transactions_24h as supporting context for on-chain activity level.
- data/onchain/netflow.json — exchange inflow/outflow/netflow (CoinMetrics), MVRV ratio, active addresses
- data/whales/large_transactions.json — transactions ≥500 BTC, source and count
- data/macro/fear_greed_7d.json — fear/greed index
- data/macro/btc_market.json — price and market cap
- data/options/btc_options.json — put/call ratio, IV, max pain

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
    "exchange_netflow_btc": null,
    "exchange_netflow_signal": "strong_accumulation | mild_accumulation | neutral | mild_distribution | strong_distribution",
    "exchange_reserve_btc": null,
    "mvrv_ratio": null,
    "whale_tx_count_24h": 0,
    "options_pcr": null,
    "options_max_pain_weekly": null,
    "network_health": "1 sentence on transaction activity, hash rate context, and any anomalies",
    "transactions_24h": null,
    "hashrate_24h": null,
    "btc_24h_change_pct": 0.0,
    "btc_market_cap_usd": 0,
    "accumulation_signal": "strong | moderate | neutral | distribution",
    "top_onchain_signal": "the single most significant observation"
  }
}

## Signal interpretation
- netflow_btc positive = more BTC leaving exchanges = accumulation (bullish)
- MVRV < 1.0 = undervalued; 1-2 = fair; 2-3.5 = overvalued; >3.5 = extreme (bubble risk)
- PCR > 1.2 = bearish hedge; PCR < 0.7 = complacency/bullish
- Max pain: price gravitates toward this strike at expiry
- hashrate_24h rising = network security increasing, miner confidence signal
- transactions_24h > 700k = high on-chain activity; < 400k = low; use as context for mempool/netflow interpretation
- blockchair.json is collected every 2h; if file is >3h old, note as stale but do not abort

Write .done file LAST.
