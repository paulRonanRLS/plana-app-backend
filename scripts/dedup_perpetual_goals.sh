#!/usr/bin/env bash
# Release duplicate active perpetual goals that share the same metric type.
#
# Usage:
#   ./scripts/dedup_perpetual_goals.sh           # apply changes
#   ./scripts/dedup_perpetual_goals.sh --dry-run # preview only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

export CLAUDE_ENABLED=false
export TELEGRAM_ENABLED=false
export GARMIN_ENABLED=false
export STRAVA_ENABLED=false
export REDIS_ENABLED=false

poetry run python scripts/dedup_perpetual_goals.py "$@"
