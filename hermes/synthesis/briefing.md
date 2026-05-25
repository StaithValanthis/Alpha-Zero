# Synthesis Agent
# Model: cerebras/qwen-3-235b-a22b-instruct-2507 | tier: critical

## Inputs (all required)
- data/proposed_hypotheses.json
- data/bull_round1.json + data/bull_round2.json
- data/bear_round1.json + data/bear_round2.json
- data/analyst_reports/technical_analyst.json
- data/analyst_reports/derivatives_analyst.json
- data/analyst_reports/onchain_macro_analyst.json
- data/analyst_reports/sentiment_news_analyst.json
- data/analyst_reports/options_analyst.json (optional — include if options_analyst.done exists, degrade gracefully if absent, note in data_freshness)

## Part 1: Per-hypothesis adjudication

For each hypothesis:
1. Fact-check ALL specific claims in both Bull and Bear arguments against analyst reports.
   Flag as "claim_unverified" any claim not supported by analyst data.
2. Identify which Round 2 rebuttals landed vs failed.
3. Weight surviving evidence by: (a) specificity (b) cross-analyst agreement (c) logical consistency
4. Verdict: "bull_wins" | "bear_wins" | "inconclusive"
5. Confidence: 0.0-1.0

Only "bull_wins" hypotheses are passed to Strategy Tester.

## Part 2: Write state/research.json
{
  "date": "YYYY-MM-DD",
  "produced_at": "...",
  "market_regime": "...",
  "regime_confidence": 0.0,
  "btc_dominance_trend": "...",
  "price_sentiment_divergence": "bullish | bearish | aligned",
  "sentiment_momentum": "positive | negative | neutral",
  "alt_rotation_signal": "on | off",
  "active_tier1_event": null,
  "data_freshness": "all_fresh | degraded_due_to_missing_{agent}",
  "approved_hypotheses": [...],
  "rejected_hypotheses": [...],
  "inconclusive_hypotheses": [...]
}

## Part 3: Write debate transcripts
data/debates/{hypothesis_chain_id}.json with full Bull/Bear transcript.

## NEVER promote "bear_wins" or "inconclusive" to Strategy Tester.
