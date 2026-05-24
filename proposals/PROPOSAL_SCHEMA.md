# Proposal YAML Schema (v3 — parallel-pool aware)

All proposals require the `model` block. Missing fields = auto-rejected by deployer.

```yaml
proposal_id: prop_YYYYMMDD_001
created_date: YYYY-MM-DD
created_by: chief-of-staff
status: pending | approved | rejected | deployed
agent_name: kebab-case-name
agent_role: one-line role description
schedule: "cron expression"

# ── REQUIRED model block (v3) ──────────────────────────────────────────
recommended_model: provider/model-id          # must be on verified free list
recommended_tier: critical | reasoning_bull | reasoning_bear | reasoning_solo |
                  analyst_strong | analyst_macro | analyst_technical |
                  analyst_derivatives | analyst_simple |
                  ops_chief | ops_standard | ops_mechanical |
                  classifier | builder
fallback_chain:
  - provider/model-id                         # fallback 1 (different pool)
  - provider/model-id                         # fallback 2 (Mistral free)
  - provider/model-id                         # fallback 3 (OpenRouter free)
parallel_pool_check: >
  List every other agent that runs in the same time window.
  Confirm each uses a DIFFERENT Groq model (different pool).
  If no parallel agents, state "sequential — no pool conflict".
model_justification: >
  Which Q in the decision tree triggered this tier. Why this model.
  Context window check. Parallel pool verification.
cost: $0.00/day
# ── end model block ────────────────────────────────────────────────────

estimated_cost_per_day: 0.00

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
```

## Verified Free Model Tiers (as of 2026-05-24)

| Tier               | Primary                                           | Fallback 1              | Fallback 2                  | Fallback 3                              |
|--------------------|---------------------------------------------------|-------------------------|-----------------------------|-----------------------------------------|
| critical           | cerebras/qwen-3-235b-a22b-instruct-2507           | groq/openai/gpt-oss-120b| mistral/mistral-large-latest| openrouter/minimax/minimax-m2.5:free    |
| reasoning_bull     | groq/meta-llama/llama-4-scout-17b-16e-instruct    | groq/openai/gpt-oss-120b| mistral/mistral-large-latest| openrouter/nvidia/nemotron-3-super:free |
| reasoning_bear     | groq/openai/gpt-oss-120b                          | groq/llama-4-scout      | mistral/mistral-large-latest| openrouter/nvidia/nemotron-3-super:free |
| reasoning_solo     | groq/openai/gpt-oss-120b                          | groq/llama-4-scout      | mistral/mistral-medium      | openrouter/minimax/minimax-m2.5:free    |
| analyst_strong     | cerebras/qwen-3-235b-a22b-instruct-2507           | groq/openai/gpt-oss-120b| mistral/mistral-large-latest| openrouter/minimax/minimax-m2.5:free    |
| analyst_macro      | groq/openai/gpt-oss-120b                          | groq/llama-4-scout      | mistral/mistral-medium      | openrouter/minimax/minimax-m2.5:free    |
| analyst_technical  | groq/meta-llama/llama-4-scout-17b-16e-instruct    | groq/openai/gpt-oss-120b| mistral/mistral-medium      | openrouter/llama-3.3-70b:free           |
| analyst_derivatives| groq/llama-3.3-70b-versatile                      | groq/llama-4-scout      | mistral/mistral-small       | openrouter/llama-3.3-70b:free           |
| analyst_simple     | groq/llama-3.1-8b-instant                         | groq/llama-3.3-70b      | mistral/mistral-small       | openrouter/llama-3.3-70b:free           |
| ops_chief          | groq/llama-3.3-70b-versatile                      | groq/llama-4-scout      | mistral/mistral-small       | openrouter/llama-3.3-70b:free           |
| ops_standard       | groq/llama-3.3-70b-versatile                      | groq/llama-4-scout      | mistral/mistral-small       | openrouter/llama-3.3-70b:free           |
| ops_mechanical     | groq/llama-3.1-8b-instant                         | groq/llama-3.3-70b      | mistral/open-mistral-nemo   | openrouter/llama-3.3-70b:free           |
| classifier         | gemini/gemini-2.0-flash                           | groq/llama-3.1-8b       | mistral/mistral-small       | openrouter/llama-3.3-70b:free           |
| builder            | mistral/codestral-latest                          | mistral/devstral-medium | groq/openai/gpt-oss-120b    | openrouter/minimax/minimax-m2.5:free    |

## Auto-Reject Conditions
- `cost` field > $0.00/day
- `recommended_tier` missing
- `parallel_pool_check` missing
- Model referencing: claude, anthropic, gpt-4o (non-oss), deepseek paid, dashscope
- No fallback_chain for critical or reasoning tiers
- Provider not in verified free list
- Two parallel agents on the same Groq model pool
