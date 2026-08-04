#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
TICK_INTERVAL="${TICK_INTERVAL:-5}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: $PYTHON_BIN not found or not executable."
  echo "Create the virtual environment first, then install requirements."
  exit 1
fi

exec "$PYTHON_BIN" -m src.cli notifier-run --tick-interval "$TICK_INTERVAL"
