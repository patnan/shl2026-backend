#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
TICK_INTERVAL="${TICK_INTERVAL:-30}"
SEASON_ID="${SEASON_ID:-18263}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: $PYTHON_BIN not found or not executable."
  echo "Create the virtual environment first, then install requirements."
  exit 1
fi

# Seed targets for the season (idempotent).
"$PYTHON_BIN" -m src.cli poller-seed "$SEASON_ID"

# Run poller loop.
exec "$PYTHON_BIN" -m src.cli poller-run --tick-interval "$TICK_INTERVAL"
