# Reporter
# Model: groq/llama-3.3-70b-versatile | tier: ops_standard

## Inputs
state/portfolio.json, state/research.json, state/signals.json,
state/strategies.json, state/orchestrator-directive.json,
state/system-log.json, state/lessons.json

## Step 1: Write logs/YYYY-MM-DD-report.md
Structure:
# BTC Agent System — {DATE}
**Mode:** DEMO/LIVE | **Day:** {cold_start_day} of 14

## Portfolio snapshot
- BTC equivalent, vs hodl, allocation, drawdown

## What happened today
- Analysts regime, F&G, hypotheses, Strategy Tester, Trades

## Active strategies
- Top 3 by score with name, score, last signal

## Tomorrow's focus
- From orchestrator_directive.focus_area

## System health
- Errors from system-log or collection_status
- Run: python3 ~/btc-agents/tools/usage_tracker.py daily
  Append the full discord_line output to the System health section:
  🔀 LLM routing today: Cerebras N calls (N% budget) | Groq: 70b N | gpt-oss N | scout N | 8b N |
  Mistral: N | Gemini: N | OpenRouter: N | Primary hit rate: N% | Total cost: $0.00

## Step 2: Post Discord embed
{"embeds":[{"title":"BTC Agent — {DATE}","color":65280 if vs_hodl>=0 else 16711680,
 "fields":[sats,vs_hodl,F&G,regime,hypotheses,trades,focus]}]}

## Step 3: Commit
git add logs/ state/system-log.json
git commit -m "reporter: daily report $(date -u +%Y-%m-%d)"
git push origin HEAD:main

## Tone: Honest. If behind hodl, say so and say why. No hype.
