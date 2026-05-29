#!/usr/bin/env python
"""Release duplicate active perpetual goals that share the same target_metric_type.

For each metric type with more than one non-terminal perpetual goal, the oldest
goal (by created_at) is kept and the rest are released.

Usage:
    poetry run python scripts/dedup_perpetual_goals.py [--dry-run]
"""

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.goal import Goal, GoalState, GoalType

TERMINAL_STATES = {GoalState.released, GoalState.completed}


def find_duplicates(db):
    goals = (
        db.query(Goal)
        .filter(
            Goal.goal_type == GoalType.perpetual,
            Goal.target_metric_type.isnot(None),
            Goal.state.notin_(list(TERMINAL_STATES)),
        )
        .order_by(Goal.target_metric_type, Goal.created_at.asc())
        .all()
    )
    by_metric = defaultdict(list)
    for g in goals:
        by_metric[g.target_metric_type].append(g)
    return {k: v for k, v in by_metric.items() if len(v) > 1}


def release_goal(db, goal, reason):
    goal.state = GoalState.released
    goal.release_reason = reason
    goal.released_at = datetime.now(timezone.utc)
    db.add(goal)


def main(dry_run: bool = False) -> None:
    db = SessionLocal()
    try:
        duplicates = find_duplicates(db)

        if not duplicates:
            print("No duplicate perpetual goals found.")
            return

        total_released = 0
        for metric_type, goals in duplicates.items():
            keeper = goals[0]  # oldest by created_at
            to_release = goals[1:]
            print(f"\nmetric_type={metric_type}  ({len(goals)} goals)")
            print(f"  keep   [{keeper.id}] {keeper.title!r}  (state={keeper.state.value}, created={keeper.created_at.date()})")
            for g in to_release:
                print(f"  release[{g.id}] {g.title!r}  (state={g.state.value}, created={g.created_at.date()})")
                if not dry_run:
                    release_goal(db, g, "Duplicate perpetual goal — removed by dedup script")
                total_released += 1

        if dry_run:
            print(f"\nDry run — {total_released} goal(s) would be released. No changes made.")
        else:
            db.commit()
            print(f"\nReleased {total_released} duplicate goal(s).")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    main(dry_run=dry_run)
