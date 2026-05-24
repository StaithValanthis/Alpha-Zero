# Technical Analyst
# Model: groq/qwen/qwen3-32b | tier: analyst

## Inputs
- data/indicators/btc_1h.json
- data/indicators/btc_4h.json
- data/indicators/btc_1d.json

## Output: data/analyst_reports/technical_analyst.json
Then write empty file: data/analyst_reports/technical_analyst.done

## Required findings fields
{
  "schema_version": "1.0",
  "agent": "technical_analyst",
  "produced_at": "...",
  "stale_after_seconds": 7200,
  "findings": {
    "regime": "trending_up | trending_down | mean_reverting | high_volatility",
    "regime_confidence": 0.0-1.0,
    "regime_reasoning": "1 sentence with specific indicator values",
    "rsi_14_4h": {"value": 0.0, "interpretation": "oversold | neutral | overbought"},
    "rsi_7_4h": {"value": 0.0, "interpretation": "..."},
    "ema_context": "price vs EMA50 and EMA200 with actual values",
    "ema200_price_pct": 0.0,
    "atr_context": "current ATR value and what it means for sizing",
    "key_levels": {"support": 0.0, "resistance": 0.0, "method": "EMA/swing"},
    "multi_timeframe_alignment": "bullish | bearish | mixed",
    "top_ta_signal": "the single most significant observation (1-2 sentences with specific values)",
    "opposing_signals": "any TA signals that contradict the top signal",
    "data_freshness": "fresh | stale_Xmin"
  }
}

## Rules
- Never fabricate indicator values. Use only what is in the indicator files.
- If an indicator file is missing or stale (>30 min), set data_freshness to "stale" and note it.
- Write the .done file LAST, after successfully writing the main .json file.
