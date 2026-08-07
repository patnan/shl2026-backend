#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
TICK_INTERVAL="${TICK_INTERVAL:-30}"
SEASON_IDS="${SEASON_IDS:-18263}"
PAST_SEASON_IDS="${PAST_SEASON_IDS:-}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: $PYTHON_BIN not found or not executable."
  echo "Create the virtual environment first, then install requirements."
  exit 1
fi

# Seed continuous targets for each season.
IFS=',' read -ra SEASONS <<< "$SEASON_IDS"
for sid in "${SEASONS[@]}"; do
  sid="$(echo "$sid" | xargs)"  # trim whitespace
  [[ -z "$sid" ]] && continue
  echo "Seeding season $sid (continuous)..."
  "$PYTHON_BIN" -m src.cli poller-seed "$sid"
done

# Seed one-shot targets for past seasons.
if [[ -n "$PAST_SEASON_IDS" ]]; then
  IFS=',' read -ra PAST_SEASONS <<< "$PAST_SEASON_IDS"
  for sid in "${PAST_SEASONS[@]}"; do
    sid="$(echo "$sid" | xargs)"  # trim whitespace
    [[ -z "$sid" ]] && continue
    echo "Seeding past season $sid (one-shot)..."
    "$PYTHON_BIN" -m src.cli poller-seed "$sid" --once
  done
fi

# Run poller loop.
exec "$PYTHON_BIN" -m src.cli poller-run --tick-interval "$TICK_INTERVAL"
