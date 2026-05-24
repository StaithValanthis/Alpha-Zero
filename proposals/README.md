# Agent Hiring Proposals

This directory manages the autonomous agent hiring system. Chief of Staff evaluates the agent team every Sunday at 21:00 AEST and writes proposals here when structural gaps are identified.

## Workflow

```
Chief evaluates → proposals/pending/prop_YYYYMMDD_001.yaml
Human reviews  → cp proposals/pending/prop_YYYYMMDD_001.yaml proposals/approved/
Agent deployer → runs hourly, deploys anything in approved/ within 60 minutes
```

## Directories

- `pending/` — proposals written by Chief, awaiting human review
- `approved/` — human-approved proposals ready for deployment
- `rejected/` — rejected proposals (kept for audit trail)
- `deployed/` — proposals that have been deployed (moved here after deployment)

## Approving a Proposal

Review the YAML file in `pending/`. If you approve:
```bash
cp proposals/pending/prop_YYYYMMDD_001.yaml proposals/approved/
```

The agent deployer runs every hour and will deploy the new agent within 60 minutes.

To reject:
```bash
cp proposals/pending/prop_YYYYMMDD_001.yaml proposals/rejected/
```

## Guard Rails

Every proposal must pass ALL of these before it is written:

1. **Maximum 1 proposal per week** — Chief checks for existing proposals before creating a new one
2. **Existing data only** — inputs must be files that already exist in `data/` or `state/`
3. **No trading authority** — only analysts and signal generators are proposable; no agent may call Bybit write endpoints
4. **Cost under $0.10/day** — estimated LLM cost must be below 10 cents per day
5. **Evidence required** — must cite specific files and patterns as evidence for the gap
6. **Human approval always required** — no agent is ever deployed without a file in `approved/`

## Proposal YAML Schema

```yaml
proposal_id: prop_YYYYMMDD_001
created_date: YYYY-MM-DD
created_by: chief-of-staff
status: pending | approved | rejected | deployed
agent_name: kebab-case-name
agent_role: one-line role description
schedule: "cron expression"
model: coordinator
estimated_cost_per_day: 0.05
problem_statement: |
  Evidence-backed description of the gap, citing specific files.
evidence:
  - "data/file.json: specific pattern observed"
inputs:
  - data/existing_file.json
outputs:
  - data/new_output_file.json
supplements_agent: which-existing-agent
pipeline_position: when in daily pipeline
guard_rails:
  existing_data_only: true
  no_trading_authority: true
  cost_under_10_cents: true
  no_duplicate_role: true
human_review_required: true
approval_instructions: |
  To approve: cp proposals/pending/prop_YYYYMMDD_001.yaml proposals/approved/
  To reject: cp proposals/pending/prop_YYYYMMDD_001.yaml proposals/rejected/
```
