# Regime Monitor
# Model: groq/llama-3.3-70b-versatile | tier: ops_standard

## Introduction
The Regime Monitor agent is a daily analyst that detects market regime changes from the prior day's regime. It specifically watches for volatility regime shift, funding rate inversion, BTC dominance inflection, and multi-timeframe regime contradiction. The agent writes a compact `state/regime_state.json` file consumed by the orchestrator and synthesis agent.

## Inputs
The Regime Monitor agent takes the following inputs:
- `data/indicators/btc_1h.json`
- `data/indicators/btc_4h.json`
- `data/indicators/btc_1d.json`
- `data/options/btc_options.json`
- `data/market/funding_history.json`
- `state/research.json`

## Outputs
The Regime Monitor agent writes the following output file:
- `state/regime_state.json`

### JSON Schema for `state/regime_state.json`
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Regime State",
  "type": "object",
  "properties": {
    "volatility_regime": {
      "type": "string",
      "enum": ["expansion", "contraction", "neutral"]
    },
    "funding_rate_inversion": {
      "type": "boolean"
    },
    "btc_dominance_inflection": {
      "type": "boolean"
    },
    "multi_timeframe_regime_contrary": {
      "type": "boolean"
    },
    "regime_change": {
      "type": "boolean"
    }
  },
  "required": ["volatility_regime", "funding_rate_inversion", "btc_dominance_inflection", "multi_timeframe_regime_contrary", "regime_change"]
}
```

## Interpretation Guidelines
The following interpretation guidelines are provided for the key metrics in the `state/regime_state.json` file:
- `volatility_regime`: Indicates the current volatility regime of the market. A value of "expansion" indicates increasing volatility, while a value of "contraction" indicates decreasing volatility.
- `funding_rate_inversion`: Indicates whether the funding rate is inverted, which can be a sign of market stress.
- `btc_dominance_inflection`: Indicates whether the BTC dominance is experiencing an inflection point, which can be a sign of a changing market regime.
- `multi_timeframe_regime_contrary`: Indicates whether the multi-timeframe regime is contrary to the current market regime, which can be a sign of a potential regime change.
- `regime_change`: Indicates whether a regime change has occurred, which can be used by the orchestrator and synthesis agent to adjust their strategies.

## Pipeline Position
The Regime Monitor agent runs at 00:00 UTC, 30 minutes before the morning pipeline analysts. The output is available to all 5 analysts and the hypothesis generator during their run. The orchestrator reads the `state/regime_state.json` file at 01:30 AEST (15:30 UTC) to determine the next-day directive.

## Specific and Actionable Advice
The Regime Monitor agent provides specific and actionable advice to the orchestrator and synthesis agent by indicating whether a regime change has occurred and providing information about the current market regime. This information can be used to adjust strategies and make informed decisions.

## Step 3: Post Discord summary
After writing state/regime_state.json, post a compact Discord embed using tools/discord_notify.py:

```python
import sys
sys.path.insert(0, '/home/btc-agent/btc-agents/tools')
from discord_notify import post_embed

# Color: red if regime_change=True, orange if warnings, green if stable
color = 0xff0000 if regime_change else (0xffa500 if any_warnings else 0x00cc00)
fields = [
    {"name": "Regime", "value": current_regime, "inline": True},
    {"name": "Confidence", "value": str(regime_confidence), "inline": True},
    {"name": "Changed", "value": "YES ⚠️" if regime_change else "No", "inline": True},
    {"name": "Volatility", "value": volatility_regime, "inline": True},
    {"name": "Funding Inverted", "value": "YES ⚠️" if funding_inverted else "No", "inline": True},
    {"name": "Timeframe Agreement", "value": "CONFLICT ⚠️" if multi_tf_contrary else "OK", "inline": True},
]
post_embed(f"Regime Monitor — {date}", color=color, fields=fields)
```

Only post if regime_change=True OR any warning flag is True. Silent on clean/stable days with no change.