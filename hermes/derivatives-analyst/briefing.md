# Derivatives Analyst
# Model: groq/llama-3.3-70b-versatile | tier: analyst_derivatives

## Inputs
- data/market/funding_history.json
- data/market/open_interest.json
- data/market/long_short_ratio.json

## Output: data/analyst_reports/derivatives_analyst.json
Then: data/analyst_reports/derivatives_analyst.done

## Required findings fields
{
  "schema_version": "1.0",
  "agent": "derivatives_analyst",
  "produced_at": "...",
  "stale_after_seconds": 7200,
  "findings": {
    "funding_regime": "extreme_negative | negative | neutral | positive | extreme_positive",
    "funding_rate_latest": 0.0,
    "funding_rate_7d_avg": 0.0,
    "funding_trend": "rising | falling | stable",
    "funding_signal": "accumulation_signal if extreme_negative | distribution_signal if extreme_positive | neutral",
    "oi_trend": "expanding | contracting | flat",
    "oi_change_24h_pct": 0.0,
    "long_short_bias": "crowded_long | crowded_short | balanced",
    "long_short_ratio_latest": 0.0,
    "derivatives_summary": "1-2 sentences describing overall derivatives picture",
    "perp_opportunity": "describe any funding arb if funding extreme",
    "top_derivatives_signal": "the single most actionable observation",
    "data_freshness": "fresh | stale_Xh"
  }
}

## Funding thresholds
- < -0.01%: extreme negative → accumulation signal
- -0.01% to -0.003%: negative → mild bullish lean
- -0.003% to +0.003%: neutral
- +0.003% to +0.015%: positive → mild crowding caution
- > +0.015%: extreme positive → distribution risk

Write .done file LAST.
