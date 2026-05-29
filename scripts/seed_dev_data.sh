#!/usr/bin/env bash
# Seed realistic development data — goals, milestones, and metric readings.
# Safe to run multiple times; skips goals whose title already exists.
#
# Usage:
#   ./scripts/seed_dev_data.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

export CLAUDE_ENABLED=false
export TELEGRAM_ENABLED=false
export GARMIN_ENABLED=false
export STRAVA_ENABLED=false
export REDIS_ENABLED=false

poetry run python scripts/seed_dev_data.py "$@"
