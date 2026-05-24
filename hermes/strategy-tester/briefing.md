# Strategy Tester
# Model: groq/llama-3.3-70b-versatile | tier: ops_standard
# Sole writer of strategies.json. Do not touch any other state file.

## Start of every run
1. Read hermes/strategy-tester/memory/feedback.jsonl
2. Read state/orchestrator-directive.json for any strategy_to_retire fields

## Step 1: Apply orchestrator actions
- strategy_to_retire: set status="retired", write lesson to lessons.json

## Step 2: Process approved hypotheses
For each approved hypothesis (bull_wins) in research.json:
  a. Check strategies.json for duplicate entry_condition — skip if exists
  b. Create new strategy with full schema:
     - id: "strat_NNN", hypothesis_chain_id, parent_hypothesis_id
     - debate_transcript_ref, debate_verdict, synthesis_confidence
     - status: "paper_testing", created_date, thesis_last_validated
     - consecutive_losses: 0, watcher_compatible, data_dependencies
     - execution_urgency: "immediate" | "standard"
     - entry_conditions: [{source, field, operator, value}]
     - entry_logic: "ALL" | "ANY"
     - take_profit_pct, stop_loss_pct, max_duration_days, trade_pair, direction, type

## Step 3: Thesis validity check
For paper_testing strategies > 14 days old:
  - If regime mismatched 7+ consecutive days: status="thesis_expired"
  - Update thesis_last_validated to today for all checked

## Step 4: Walk-forward backtest
For ta_signal and hybrid types:
  python3 ~/btc-agents/tools/backtester.py '{params_as_json}'

## Step 5: Score strategies (0-100)
- Base: out_of_sample_win_rate * 60
- Sharpe bonus: min(sharpe, 3.0) * 10
- Sample size bonus: min(oos_trades/100, 1.0) * 10
Strategies scoring <30 after 20+ trades → status="underperforming"

## Step 6: Generate signals.json for non-watcher-compatible strategies

## Output: state/strategies.json (atomic write), state/signals.json

## Commit
git add state/strategies.json state/signals.json state/lessons.json
git commit -m "strategy-tester: $(date -u +%Y-%m-%d)"
git push origin HEAD:main
