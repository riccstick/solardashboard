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

uv run python scripts/configure.py

echo
read -r "?Press Return to close..."
