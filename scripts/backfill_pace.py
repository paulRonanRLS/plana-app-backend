#!/usr/bin/env python
"""Backfill pace_per_km into notes JSON for existing Strava running activities.

Idempotent — skips any record that already has pace_per_km in its notes.

Usage:
    poetry run python scripts/backfill_pace.py [--dry-run]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.metric_reading import MetricReading, MetricSource, MetricType


def _calculate_pace(moving_time_s: float, distance_km: float) -> float:
    return round(moving_time_s / distance_km / 60, 2)


def main(dry_run: bool = False) -> None:
    db = SessionLocal()
    try:
        rows = (
            db.query(MetricReading)
            .filter(
                MetricReading.metric_type == MetricType.activity,
                MetricReading.source == MetricSource.strava,
            )
            .all()
        )

        total_runs = 0
        updated = 0

        for row in rows:
            try:
                notes = json.loads(row.notes) if row.notes else {}
            except (ValueError, TypeError):
                continue

            if notes.get("type", "").lower() != "run":
                continue

            total_runs += 1

            if "pace_per_km" in notes:
                continue

            distance_km = notes.get("distance_km") or 0
            moving_time_s = notes.get("moving_time_s") or 0

            if distance_km <= 0 or moving_time_s <= 0:
                continue

            notes["pace_per_km"] = _calculate_pace(moving_time_s, distance_km)

            if not dry_run:
                row.notes = json.dumps(notes)
                db.add(row)

            updated += 1

        if dry_run:
            print(f"Dry run — would update {updated} of {total_runs} running activities with pace_per_km")
        else:
            db.commit()
            print(f"Updated {updated} of {total_runs} running activities with pace_per_km")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
