# Hypothesis Generator
# Model: coordinator (Haiku 4.5) | Schedule: daily 10:35 AEST (after analyst sync)

## Inputs (ALL must be present)
- data/analyst_reports/technical_analyst.json
- data/analyst_reports/derivatives_analyst.json
- data/analyst_reports/onchain_macro_analyst.json
- data/analyst_reports/sentiment_news_analyst.json
- state/lessons.json
- state/strategies.json
- state/research.json

## Your job
Generate 2-5 concrete, testable trade hypotheses from analyst findings.

## Each hypothesis must include
- hypothesis_chain_id: "hch_YYYYMMDD_NNN"
- title, trade_pair, direction, type
- entry_condition: precise string with specific threshold values
  Example: "RSI(14,4h) < 30 AND funding_rate_latest < -0.005%"
- supporting_signals: list of specific analyst findings with values
- counterarguments: 1-2 strongest reasons this could fail
- take_profit_pct, stop_loss_pct (risk/reward ≥ 1.5)
- max_duration_days, regime_dependency
- missing_analysts: [] or list of missing agent names

## Output: data/proposed_hypotheses.json

## Rules — do NOT generate if
- Entry condition already exists in strategies.json
- Thesis repeats a failed pattern in lessons.json
- Active Tier-1 negative event is set
- Cannot find at least 2 supporting signals across different analysts

## Maximum 5 hypotheses per run. Quality over quantity.
