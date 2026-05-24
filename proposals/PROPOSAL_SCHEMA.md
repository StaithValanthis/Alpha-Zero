# Proposal YAML Schema (v2 — with model fields)

All proposals must include the `model` block. Proposals without it will be auto-rejected by the deployer.

```yaml
proposal_id: prop_YYYYMMDD_001
created_date: YYYY-MM-DD
created_by: chief-of-staff
status: pending | approved | rejected | deployed
agent_name: kebab-case-name
agent_role: one-line role description
schedule: "cron expression"

# REQUIRED: model block (added 2026-05-24)
model:
  tier: critical | reasoning | analyst | ops | classifier
  primary: provider/model-id        # must be on verified free list
  fallbacks:
    - provider/model-id             # at least 1 fallback for critical/reasoning
cost_usd_per_run: 0.00              # must be 0.00; > 0 = auto-reject

estimated_cost_per_day: 0.00       # LLM cost; must be 0.00 with free models

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
  To reject:  cp proposals/pending/prop_YYYYMMDD_001.yaml proposals/rejected/
```

## Verified Free Model Tiers (as of 2026-05-24)

| Tier        | Primary                                    | Fallback 1                  | Fallback 2                               | Fallback 3                                        |
|-------------|--------------------------------------------|-----------------------------|------------------------------------------|---------------------------------------------------|
| critical    | cerebras/qwen-3-235b-a22b-instruct-2507    | groq/qwen/qwen3-32b         | groq/openai/gpt-4o-mini-oss              | groq/llama-3.3-70b-versatile                      |
| reasoning   | groq/qwen/qwen3-32b                        | cerebras/qwen-3-235b-a22b-instruct-2507 | groq/openai/gpt-4o-mini-oss  | groq/llama-3.3-70b-versatile                      |
| analyst     | cerebras/qwen-3-235b-a22b-instruct-2507    | groq/qwen/qwen3-32b         | groq/llama-3.3-70b-versatile             | groq/meta-llama/llama-4-scout-17b-16e-instruct    |
| ops         | groq/llama-3.3-70b-versatile               | groq/meta-llama/llama-4-scout-17b-16e-instruct | cerebras/llama3.1-8b      |                                                   |
| classifier  | google/gemini-2.0-flash                    | groq/meta-llama/llama-4-scout-17b-16e-instruct |                           |                                                   |

## Auto-Reject Conditions
- `cost_usd_per_run` > 0.00
- `model.tier` missing
- Any model ID referencing: claude, anthropic, gpt-4o (non-oss), mistral, deepseek, glm, zai
- No fallbacks for critical or reasoning tier
- Provider not in verified free list
