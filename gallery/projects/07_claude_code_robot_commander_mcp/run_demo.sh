#!/usr/bin/env bash
# One-shot demo: gateway -> client-sandbox node -> commander(MCP)
# Author: Silan Hu (silan.hu@u.nus.edu)

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if command -v uv >/dev/null 2>&1; then
    PY=(uv run --no-sync python)
else
    PY=(python)
fi

PORT="${EASYREMOTE_PORT:-8085}"
GATEWAY="127.0.0.1:${PORT}"
USER_ID="${USER_ID:-demo-user}"
NODE_ID="${NODE_ID:-robot-sandbox-${USER_ID}}"

PIDS=()
cleanup() {
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
}
trap cleanup EXIT

echo "=== [1/3] Starting gateway server on port ${PORT} ==="
EASYREMOTE_PORT="$PORT" "${PY[@]}" server.py &
PIDS+=($!)
sleep 3

echo "=== [2/3] Starting client-sandbox node (${NODE_ID}) ==="
EASYREMOTE_GATEWAY_ADDRESS="$GATEWAY" \
USER_ID="$USER_ID" \
NODE_ID="$NODE_ID" \
"${PY[@]}" client_sandbox_node.py &
PIDS+=($!)
sleep 5

echo "=== [3/3] Running commander client through MCP tools ==="
EASYREMOTE_GATEWAY_ADDRESS="$GATEWAY" \
TARGET_USER_ID="$USER_ID" \
TARGET_USER_NODE_ID="${TARGET_USER_NODE_ID:-}" \
MISSION_ID="${MISSION_ID:-mission-robot-inspection}" \
MISSION_STEPS="${MISSION_STEPS:-boot,inspect,report}" \
ROBOT_ACTION="${ROBOT_ACTION:-forward}" \
ROBOT_DISTANCE_M="${ROBOT_DISTANCE_M:-1.5}" \
"${PY[@]}" commander_client.py

echo ""
echo "=== Output files ==="
ls -lh "$DIR"/robot-mission.json 2>/dev/null || true
echo "=== Done ==="
