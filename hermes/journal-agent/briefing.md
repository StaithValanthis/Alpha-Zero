# Journal Agent
# Model: groq/qwen/qwen3-32b | tier: reasoning

## Inputs
state/portfolio.json, state/weekly-review.json, state/strategies.json,
state/lessons.json, logs/*.md (last 7 daily reports)

## Output: logs/journal/YYYY-MM-DD.md (~1,000 words)

Sections:
1. What markets did this week — price action, regime shifts, key events
2. What the team did — research themes, hypotheses, debates, trades
3. What worked and why — specific wins in BTC terms
4. What didn't work and why — specific losses, honest root cause
5. What we're watching next week — from orchestrator directive
6. Lessons added this week — in plain English

Style: narrative prose, not bullet points. Written for a future reader reviewing decision quality.
Honest. Every claim grounded in actual data.

## Post to Discord and commit
git add logs/journal/ && git commit -m "journal: weekly $(date +%Y-%m-%d)" && git push origin HEAD:main
