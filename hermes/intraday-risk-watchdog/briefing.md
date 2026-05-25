# Intraday Risk Watchdog
# Model: none | tier: no_llm

## Overview
The Intraday Risk Watchdog agent is a no-LLM daemon that monitors the `ws_prices.json` file for flash crash, funding rate inversion, and stablecoin depeg proxy events. When a trigger event occurs, the agent sets `auto_pause_signal_watcher` to `true` in `anomaly_state.json`, posts an urgent Discord embed, and writes an entry to `state/system-log.json`. The agent resets `auto_pause` only when the price recovers the threshold and 30 minutes have elapsed.

## Inputs
- `data/market/ws_prices.json`
- `data/market/funding_history.json`

## Outputs
- `state/anomaly_state.json`
  ```json
  {
    "auto_pause_signal_watcher": boolean
  }
  ```
- `state/system-log.json` (append on trigger)
  ```json
  {
    "timestamp": string,
    "event": string,
    "description": string
  }
  ```
- Discord webhook (urgent embed on trigger only)
  ```json
  {
    "title": string,
    "description": string,
    "fields": [
      {
        "name": string,
        "value": string,
        "inline": boolean
      }
    ]
  }
  ```

## Interpretation Guidelines
- `auto_pause_signal_watcher`: When `true`, the trading system should pause until the price recovers and 30 minutes have elapsed.
- `system-log.json` entries: Monitor for repeated or persistent trigger events, which may indicate a larger market issue.
- Discord embeds: Respond promptly to urgent embeds, as they indicate a potential flash crash or funding rate inversion.

## Specific and Actionable Advice
- Monitor `ws_prices.json` for flash crash events (>=5% drop in one 5-min tick) and funding rate inversion events (extreme negative < -0.03%).
- When a trigger event occurs, set `auto_pause_signal_watcher` to `true` and post an urgent Discord embed.
- Reset `auto_pause` only when the price recovers the threshold and 30 minutes have elapsed.
- Review `system-log.json` entries regularly to identify potential issues and adjust the trading system accordingly.

## Pipeline Position
The Intraday Risk Watchdog agent operates as a standalone daemon, independent of other agents in the pipeline.

## Supplements
None.