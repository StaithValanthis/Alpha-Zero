# Pending Actions

## options-analyst deployment

**Status:** Proposal `prop_20260524_001` is in `proposals/approved/` with `status: approved`.
The `btc-agent-deployer-hourly` Hermes cron runs every hour (next: 12:00 UTC) and will auto-deploy.

**If the deployer fails to pick it up**, run manually in Discord or Hermes WebUI:

```
!deploy prop_20260524_001
```

**What the deployer will create:**
- `hermes/options-analyst/briefing.md`
- `hermes-skills/btc-agents/btc-options-analyst/SKILL.md`
- Hermes cron: `btc-options-analyst-daily` at `30 0 * * *`
- Moves proposal to `proposals/deployed/prop_20260524_001.yaml`

**Why this matters:** `data/options/btc_options.json` (PCR 1.13, max pain $76K, IV skew +0.05)
was present in all 4 debates today but never cited. This agent closes that blind spot.
