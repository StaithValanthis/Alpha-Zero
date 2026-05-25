---
name: btc-agent-deployer
description: Hourly deployer — checks proposals/approved/ and deploys any approved agent proposals.
triggers:
  - cron: "0 * * * *"
---

## Task

You are the BTC Agent Deployer. Check for approved proposals and deploy them.

### Step 1: Check for approved proposals

```bash
ls proposals/approved/*.yaml 2>/dev/null
```

If `proposals/approved/` is empty or has no `.yaml` files: **stop immediately** (nothing to do).

### Step 2: For each approved proposal — read type field FIRST

Read the full proposal YAML file. The `type` field determines the deployment path:

- `type: new_agent` → follow Step 3A (create new agent)
- `type: operational_change` → follow Step 3B (patch existing briefings only)

### Step 3A: New agent deployment (type: new_agent)

**Check recommended_tier BEFORE registering the cron.**

If `recommended_tier: no_llm`:
- This is a no-LLM watchdog/script. Do NOT create a `--skill` cron job.
- The script must already exist at `services/{script_name}.py` or `collectors/{script_name}.py`.
- If the script does not exist, STOP and log: "BLOCKED: no_llm proposal {id} requires a Python script at services/{agent_name}.py — write the script first, then re-run deployer."
- Register with: `hermes cron create "{schedule}" --name {agent_name} --script {script_path} --no-agent --workdir /home/btc-agent/btc-agents`
- Do NOT write a briefing.md or SKILL.md for no_llm agents.

If `recommended_tier` is anything else (ops_standard, critical, analyst_*, etc.):
- **Write the agent briefing**: Create `hermes/{agent_name}/briefing.md` as a complete, detailed briefing following the same style and structure as existing briefings in `hermes/`. Include:
  - Agent role and model (from recommended_model + recommended_tier)
  - All inputs to read
  - Step-by-step execution instructions
  - Output files to write
  - Commit instructions
- **Write the skill file**: Create `hermes-skills/btc-agents/{agent_name}/SKILL.md` (skills are **directories**, not flat `.md` files) using `hermes-skills/btc-agents/btc-reporter/SKILL.md` as a template. Fill in:
  - Frontmatter with name, description, and cron trigger from the proposal
  - Task instructions pointing to the new briefing
  - Commit and Discord notification steps
- **Register the Hermes cron** — schedule is a **positional argument**, not a flag:
  ```bash
  hermes cron create "{schedule}" --name {agent_name}-daily --skill {agent_name} --workdir /home/btc-agent/btc-agents
  ```
  Example: `hermes cron create "30 0 * * *" --name options-analyst-daily --skill options-analyst --workdir /home/btc-agent/btc-agents`
  Output includes the job ID — save it in the system-log deployment entry.

### Step 3B: Operational change deployment (type: operational_change)

These proposals patch existing briefings or register existing scripts — they do NOT create new agents.

Read the `required_changes` section of the proposal. For each change:

- If the change is a **briefing patch**: Use the `patch` tool to apply the exact diff described. Do not rewrite the whole briefing.
- If the change is a **model header change**: Patch only the `# Model:` line.
- If the change is a **cron registration** (e.g., registering an existing collector script as a daily cron):
  - Check that the script exists first.
  - Register with `hermes cron create ...` using `--script` and `--no-agent` if it is a plain Python script with no LLM.
  - Register with `--skill` only if the proposal specifies a skill-based run.
- Do NOT create new briefing.md or SKILL.md files for operational_change proposals.
- After applying all changes, move the proposal to deployed/ and commit.

**Update system-log.json**: Append a deployment entry with timestamp, agent_name, and "deployed by agent-deployer".
⚠️ **Use the `patch` tool**, not shell scripts or `execute_code`. Both `python3 << 'HEREDOC'` and piped `cat | python3` are blocked by the security scanner. Use `patch` to replace the closing array bracket / `last_updated` line with the new entry appended. Pattern:
```
old: last entry in events array + closing brackets
new: last entry + new deployment object + updated last_updated timestamp
```

**Move the proposal**: `mv proposals/approved/{filename} proposals/deployed/{filename}`

**Post Discord embed** (green, 65280):
- Title: "New Agent Deployed: {agent_name}"
- Fields: role, schedule, inputs, outputs

**Commit everything**:
```bash
git add hermes/{agent_name}/ hermes-skills/btc-agents/ proposals/ state/
git commit -m "deploy: {agent_name} agent from approved proposal"
git push origin HEAD:main
```
