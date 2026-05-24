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

### Step 2: For each approved proposal

Read the full proposal YAML file.

**Write the agent briefing**: Create `hermes/{agent_name}/briefing.md` as a complete, detailed briefing following the same style and structure as existing briefings in `hermes/`. Include:
- Agent role and model
- All inputs to read
- Step-by-step execution instructions
- Output files to write
- Commit instructions

**Write the skill file**: Create `hermes-skills/btc-agents/{agent_name}.md` using `hermes-skills/btc-agents/btc-reporter.md` as a template. Fill in:
- Frontmatter with name, description, and cron trigger from the proposal
- Task instructions pointing to the new briefing
- Commit and Discord notification steps

**Register the Hermes cron**:
```bash
hermes cron create --name {agent_name}-daily --schedule "{schedule}" --skill {agent_name} --workdir /home/btc-agent/btc-agents
```

**Update system-log.json**: Append a deployment entry with timestamp, agent_name, and "deployed by agent-deployer".

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
