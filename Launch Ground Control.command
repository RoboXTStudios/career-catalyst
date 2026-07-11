#!/bin/zsh

set -euo pipefail

REPO_DIR="${0:A:h}"
PORT=8504
URL="http://127.0.0.1:${PORT}/"

cd "$REPO_DIR"

if /usr/bin/curl -fsS "$URL" >/dev/null 2>&1; then
    [[ "${GROUND_CONTROL_SKIP_BROWSER:-0}" == "1" ]] || /usr/bin/open "$URL"
    exit 0
fi

echo "Starting Ground Control at $URL"
PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/ground-control-pycache" \
    /usr/bin/python3 -m streamlit run ground_control/app.py \
    --server.port "$PORT" \
    --server.headless true &
SERVER_PID=$!

cleanup() {
    kill "$SERVER_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for attempt in {1..40}; do
    if /usr/bin/curl -fsS "$URL" >/dev/null 2>&1; then
        [[ "${GROUND_CONTROL_SKIP_BROWSER:-0}" == "1" ]] || /usr/bin/open "$URL"
        echo "Ground Control is ready. Keep this window open while using the app."
        wait "$SERVER_PID"
        exit $?
    fi
    sleep 0.25
done

echo "Ground Control did not start successfully on port $PORT."
exit 1
