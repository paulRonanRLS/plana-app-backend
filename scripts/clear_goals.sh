#!/usr/bin/env bash
# Delete all goals, milestones, and sacrifices from the database.
# Leaves metric_readings intact. Safe to run before re-seeding.
#
# Usage:
#   ./scripts/clear_goals.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

export CLAUDE_ENABLED=false
export TELEGRAM_ENABLED=false
export GARMIN_ENABLED=false
export STRAVA_ENABLED=false
export REDIS_ENABLED=false

poetry run python scripts/clear_goals.py "$@"
