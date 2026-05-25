#!/usr/bin/env bash
# Restore workspace chat to the production default (cerebras/qwen-3-235b).

set -e
curl -sf -X PATCH http://127.0.0.1:3000/api/hermes-config \
  -H "Content-Type: application/json" \
  -d '{"action":"set-default-model","providerId":"cerebras","modelId":"qwen-3-235b-a22b-instruct-2507"}' > /dev/null

echo ""
echo "Workspace chat → cerebras/qwen-3-235b-a22b-instruct-2507 (restored)"
echo ""
