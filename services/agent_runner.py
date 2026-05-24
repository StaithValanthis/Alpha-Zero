"""
agent_runner.py — Invokes a single agent by name using the Anthropic SDK.
Each agent receives its briefing.md as system prompt + file tools to read/write state.
"""
import os, json, subprocess, time, requests, anthropic
from datetime import datetime, timezone
from pathlib import Path

B = Path(os.path.expanduser("~/btc-agents"))

def load_env():
    env = {}
    with open(B / ".env") as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

ENV = load_env()

# Use LiteLLM proxy aliases defined in litellm_config.yaml
MODEL_MAP = {
    "orchestrator":            "analyst",
    "bull-researcher":         "analyst",
    "bear-researcher":         "analyst",
    "trader-entry":            "analyst",
    "journal-agent":           "analyst",
    "technical-analyst":       "coordinator",
    "derivatives-analyst":     "coordinator",
    "onchain-macro-analyst":   "coordinator",
    "sentiment-news-analyst":  "coordinator",
    "hypothesis-generator":    "coordinator",
    "synthesis":               "coordinator",
    "strategy-tester":         "coordinator",
    "risk-manager":            "coordinator",
    "trader-management":       "coordinator",
    "reporter":                "coordinator",
    "builder":                 "builder",
}

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from the btc-agents directory. Path is relative to ~/btc-agents/",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path e.g. state/portfolio.json"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Atomically write content to a file. Path relative to ~/btc-agents/",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path e.g. state/research.json"},
                "content": {"type": "string", "description": "Full file content to write"}
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "run_shell",
        "description": "Run a shell command in ~/btc-agents/. Use for git commits, python scripts, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"}
            },
            "required": ["command"]
        }
    },
    {
        "name": "post_discord",
        "description": "Post a message or embed to the Discord webhook.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Plain text message (optional)"},
                "embed_title": {"type": "string", "description": "Embed title (optional)"},
                "embed_description": {"type": "string", "description": "Embed body (optional)"},
                "embed_color": {"type": "integer", "description": "Embed color int e.g. 65280 green, 16711680 red, 16776960 amber"}
            }
        }
    },
    {
        "name": "list_files",
        "description": "List files in a directory. Path relative to ~/btc-agents/",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path e.g. data/analyst_reports"}
            },
            "required": ["path"]
        }
    }
]


def handle_tool(tool_name, tool_input):
    """Execute a tool call and return the result string."""
    try:
        if tool_name == "read_file":
            path = B / tool_input["path"]
            if not path.exists():
                return f"FILE_NOT_FOUND: {tool_input['path']}"
            return path.read_text()

        elif tool_name == "write_file":
            path = B / tool_input["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(path) + ".tmp"
            with open(tmp, "w") as f:
                f.write(tool_input["content"])
            os.rename(tmp, str(path))
            return f"OK: wrote {len(tool_input['content'])} chars to {tool_input['path']}"

        elif tool_name == "run_shell":
            result = subprocess.run(
                tool_input["command"], shell=True,
                cwd=str(B), capture_output=True, text=True, timeout=120
            )
            out = (result.stdout + result.stderr).strip()
            return f"exit={result.returncode}\n{out[:2000]}"

        elif tool_name == "post_discord":
            webhook = ENV.get("DISCORD_WEBHOOK_URL", "")
            if not webhook:
                return "SKIP: DISCORD_WEBHOOK_URL not set"
            payload = {}
            if tool_input.get("content"):
                payload["content"] = tool_input["content"]
            if tool_input.get("embed_title") or tool_input.get("embed_description"):
                embed = {}
                if tool_input.get("embed_title"): embed["title"] = tool_input["embed_title"]
                if tool_input.get("embed_description"): embed["description"] = tool_input["embed_description"]
                if tool_input.get("embed_color"): embed["color"] = tool_input["embed_color"]
                payload["embeds"] = [embed]
            r = requests.post(webhook, json=payload, timeout=10)
            return f"discord: HTTP {r.status_code}"

        elif tool_name == "list_files":
            path = B / tool_input["path"]
            if not path.exists():
                return f"DIRECTORY_NOT_FOUND: {tool_input['path']}"
            files = [str(p.relative_to(B)) for p in sorted(path.iterdir())]
            return "\n".join(files)

        else:
            return f"UNKNOWN_TOOL: {tool_name}"

    except Exception as e:
        return f"TOOL_ERROR: {e}"


def run_agent(agent_name, extra_context=""):
    """
    Run a single agent by name.
    Returns: {"status": "success"|"error", "message": str, "duration_seconds": float}
    """
    start = time.time()
    briefing_path = B / "hermes" / agent_name / "briefing.md"

    if not briefing_path.exists():
        return {"status": "error", "message": f"Briefing not found: {briefing_path}"}

    briefing = briefing_path.read_text()
    model = MODEL_MAP.get(agent_name, "claude-haiku-4-5-20251001")

    # Use LiteLLM proxy for routing
    client = anthropic.Anthropic(
        api_key="btc-agents-litellm",
        base_url="http://localhost:4000"
    )

    user_message = (
        f"Execute your briefing now. Today is {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.\n"
        f"Your base directory is ~/btc-agents/\n"
        f"\nCRITICAL TOOL USAGE RULES:\n"
        f"- You MUST call read_file to read any input file. Do not assume file contents.\n"
        f"- You MUST call write_file to write every output file. Do not just describe what you would write.\n"
        f"- You MUST call write_file for EVERY file your briefing says to write, including .done markers.\n"
        f"- If your briefing says write X.json then write X.done, call write_file TWICE.\n"
        f"- Never skip a write_file call. Returning text instead of calling write_file = task failed.\n"
        f"\nWork through every step in your briefing in order. Call tools. Do not describe. Do.\n"
    )
    if extra_context:
        user_message += f"\nAdditional context:\n{extra_context}"

    messages = [{"role": "user", "content": user_message}]

    print(f"[{agent_name}] Starting ({model})...")

    try:
        for attempt in range(3):
            response = client.messages.create(
                model=model,
                max_tokens=8192,
                system=briefing,
                messages=messages,
                tools=TOOLS
            )

            # Agentic loop — keep going until end_turn or no more tool calls
            while response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        print(f"  [{agent_name}] tool: {block.name}({list(block.input.keys())})")
                        result = handle_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                # Continue conversation with tool results
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": tool_results}
                ]
                response = client.messages.create(
                    model=model,
                    max_tokens=8192,
                    system=briefing,
                    messages=messages,
                    tools=TOOLS
                )

            # Extract final text
            final_text = " ".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )
            duration = round(time.time() - start, 1)
            print(f"  [{agent_name}] Done in {duration}s")
            return {"status": "success", "message": final_text[:500], "duration_seconds": duration}

    except Exception as e:
        duration = round(time.time() - start, 1)
        print(f"  [{agent_name}] ERROR: {e}")
        return {"status": "error", "message": str(e), "duration_seconds": duration}
