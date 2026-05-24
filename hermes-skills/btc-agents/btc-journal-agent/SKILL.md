---
name: btc-journal-agent
description: Weekly journal — ~1000 word narrative review every Sunday. Posts summary to Discord.
triggers:
  - cron: "0 10 * * 0"
---

## Task

You are a delegated subagent running as the BTC Journal Agent. This runs every Sunday at 20:00 AEST.

**Read your briefing first**: `hermes/journal-agent/briefing.md` — follow it completely.

### Inputs
- `state/portfolio.json`
- `state/weekly-review.json`
- `state/strategies.json`
- `state/lessons.json`
- Last 7 daily reports from `logs/` (YYYY-MM-DD-report.md files)

### Step 1: Write journal entry
Write approximately 1000 words to `logs/journal/YYYY-MM-DD.md`.
Create the `logs/journal/` directory if it doesn't exist.

The journal should cover:
- Week's performance narrative (sats vs hodl, what worked, what failed)
- Strategy highlights and lowlights
- Key market conditions that shaped decisions
- Lessons learned and whether previous lessons were applied
- Looking ahead — what to watch next week

### Step 2: Post Discord summary
Post a concise embed to `$DISCORD_WEBHOOK_URL` with the key takeaways (3-5 bullets).

### Step 3: Commit
```bash
mkdir -p logs/journal
git add logs/journal/
git commit -m "journal: weekly entry $(date -u +%Y-%m-%d)"
git push origin HEAD:main
```
