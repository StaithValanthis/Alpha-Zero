#!/usr/bin/env bash
# Switch workspace chat to Claude Sonnet 4.6 for manual analysis sessions.
# Uses the workspace API to update btc-agent's config — no gateway restart needed.

set -e
curl -sf -X PATCH http://127.0.0.1:3000/api/hermes-config \
  -H "Content-Type: application/json" \
  -d '{"action":"set-default-model","providerId":"anthropic","modelId":"claude-sonnet-4-6"}' > /dev/null

echo ""
echo "Workspace chat → Claude Sonnet 4.6 (Anthropic)"
echo "Start a NEW chat session in the workspace."
echo "Run use-default.sh when done to restore cerebras/qwen-3-235b."
echo ""
