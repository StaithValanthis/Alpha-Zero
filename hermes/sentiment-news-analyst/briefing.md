# Sentiment/News Analyst
# Model: coordinator (Haiku 4.5) | Schedule: daily 10:30 AEST (parallel)
# YOU MAY use web search for breaking news. Do NOT use web search for price/indicator data.

## Inputs
- data/macro/fear_greed_7d.json (for context)
- Web search for: "Bitcoin news today", regulatory developments, ETF flows, exchange incidents

## Output: data/analyst_reports/sentiment_news_analyst.json
Then: data/analyst_reports/sentiment_news_analyst.done

## Required findings fields
{
  "schema_version": "1.0",
  "agent": "sentiment_news_analyst",
  "produced_at": "...",
  "stale_after_seconds": 7200,
  "findings": {
    "active_tier1_event": null,
    "sentiment_summary": "2 sentences on current market narrative and tone",
    "social_momentum": "positive | negative | neutral",
    "narrative_trend": "accumulation narrative | distribution narrative | uncertainty | neutral",
    "news_risk_level": "low | medium | high",
    "breaking_news": [],
    "top_sentiment_signal": "the single most significant observation"
  }
}

## Tier-1 events (urgency=immediate)
- Exchange hack or insolvency
- Government ban on BTC trading in G20 nation
- ETF approval or mass rejection
- US Federal Reserve emergency rate decision
- Stablecoin depeg affecting USDT or USDC

Write .done file LAST.
