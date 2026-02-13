#!/usr/bin/env bash
# One-shot demo: server -> node -> client (photo + video recording)
# Author: Silan Hu (silan.hu@u.nus.edu)

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if command -v uv >/dev/null 2>&1; then
    PY=(uv run python)
else
    PY=(python)
fi

PORT="${EASYREMOTE_PORT:-8084}"
GATEWAY="127.0.0.1:${PORT}"
USER_ID="${USER_ID:-demo-user}"
NODE_ID="${NODE_ID:-user-device-${USER_ID}}"

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

echo "=== [2/3] Starting user device node (${NODE_ID}) ==="
EASYREMOTE_GATEWAY_ADDRESS="$GATEWAY" \
USER_ID="$USER_ID" \
NODE_ID="$NODE_ID" \
CAMERA_CANDIDATES="${CAMERA_CANDIDATES:-0,1,2,3}" \
OPENCV_AVFOUNDATION_SKIP_AUTH="${OPENCV_AVFOUNDATION_SKIP_AUTH:-1}" \
"${PY[@]}" user_device_node.py &
PIDS+=($!)
sleep 5

echo "=== [3/3] Running agent client (photo + video) ==="
EASYREMOTE_GATEWAY_ADDRESS="$GATEWAY" \
TARGET_USER_ID="$USER_ID" \
PHOTO_SOURCE="${PHOTO_SOURCE:-auto}" \
PHOTO_RESOLUTION="${PHOTO_RESOLUTION:-1280x720}" \
CAMERA_SCAN_MAX_INDEX="${CAMERA_SCAN_MAX_INDEX:-6}" \
VIDEO_DURATION="${VIDEO_DURATION:-3}" \
VIDEO_FPS="${VIDEO_FPS:-30}" \
"${PY[@]}" agent_client.py

echo ""
echo "=== Output files ==="
ls -lh "$DIR"/customer-selfie.jpg "$DIR"/site-check.mp4 2>/dev/null || true
echo "=== Done ==="
