---
name: btc-morning-pipeline
description: Daily morning pipeline — runs all 4 analysts in parallel, then debate rounds, then synthesis. Posts result to Discord.
triggers:
  - cron: "30 0 * * *"
---

## Task

You are a delegated subagent running the BTC Morning Pipeline. Orchestrate the full analyst-debate-synthesis sequence.

### Stage 0: Clean slate
Delete any stale .done markers from yesterday:
```bash
rm -f data/analyst_reports/*.done
```

### Stage 1: Run all 4 analysts in parallel via delegate_task

**Technical Analyst**: Read `hermes/technical-analyst/briefing.md`. Write `data/analyst_reports/technical_analyst.json`, then write `data/analyst_reports/technical_analyst.done` last (atomically after JSON is complete).

**Derivatives Analyst**: Read `hermes/derivatives-analyst/briefing.md`. Write `data/analyst_reports/derivatives_analyst.json`, then `data/analyst_reports/derivatives_analyst.done`.

**OnChain/Macro Analyst**: Read `hermes/onchain-macro-analyst/briefing.md`. Write `data/analyst_reports/onchain_macro_analyst.json`, then `data/analyst_reports/onchain_macro_analyst.done`.

**Sentiment/News Analyst**: Read `hermes/sentiment-news-analyst/briefing.md`. Use web search for recent BTC/crypto news. Write `data/analyst_reports/sentiment_news_analyst.json`, then `data/analyst_reports/sentiment_news_analyst.done`.

### Stage 2: Verify completion
After all delegates return, count `.done` files on disk (not just delegate return status):
```bash
ls data/analyst_reports/*.done 2>/dev/null | wc -l
```
- Fewer than 2: **ABORT** — post WARNING to Discord, update `state/pipeline_state.json` with failed status. Stop.
- 2 or 3: **DEGRADED MODE** — post warning to Discord but continue with available reports.
- 4: Full run. Continue.

### Stage 3: Hypothesis generation
Delegate Hypothesis Generator: reads `hermes/hypothesis-generator/briefing.md` and all available analyst reports, writes `data/proposed_hypotheses.json`.

### Stage 4: Debate Round 1 (parallel)
- Delegate Bull Researcher: reads `hermes/bull-researcher/briefing.md`, `data/proposed_hypotheses.json`, all analyst reports → writes `data/bull_round1.json`
- Delegate Bear Researcher: reads `hermes/bear-researcher/briefing.md`, `data/proposed_hypotheses.json`, all analyst reports → writes `data/bear_round1.json`

### Stage 5: Debate Round 2 (parallel)
- Delegate Bull Researcher Round 2: reads `hermes/bull-researcher/briefing.md`, previous bull_round1.json AND `data/bear_round1.json` → writes `data/bull_round2.json`
- Delegate Bear Researcher Round 2: reads `hermes/bear-researcher/briefing.md`, previous bear_round1.json AND `data/bull_round1.json` → writes `data/bear_round2.json`

### Stage 6: Synthesis
Delegate Synthesis Agent: reads `hermes/synthesis/briefing.md`, reads all 4 debate files (bull_round1, bear_round1, bull_round2, bear_round2), adjudicates, writes `state/research.json`. Also write debate transcripts to `data/debates/YYYY-MM-DD-debate.json`.

### Stage 7: Update pipeline state
Update `state/pipeline_state.json`: mark morning-pipeline as completed_today.

### Discord notification
Post pipeline summary embed: analysts completed (N/4), regime, top hypothesis, debate winner summary.

**Note**: Do NOT run Strategy Tester — it has its own separate cron at 12:30 AEST.
