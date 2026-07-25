#!/bin/zsh

set -u

PROJECT_DIR="${0:A:h:h:h}"
cd "$PROJECT_DIR" || exit 1

if ! command -v uv >/dev/null 2>&1; then
    echo "Solar Dashboard needs uv, but uv was not found."
    echo "Install it from https://docs.astral.sh/uv/ and try again."
    read -r "?Press Return to close..."
    exit 1
fi

export PORT="${PORT:-8000}"
DASHBOARD_URL="http://127.0.0.1:${PORT}"

echo "Starting Solar Dashboard at ${DASHBOARD_URL}"
echo "Press Ctrl+C to stop it."

(
    sleep 2
    open "$DASHBOARD_URL"
) &

exec uv run python app.py
