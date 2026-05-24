#!/usr/bin/env python
"""Delete all goals, milestones, and sacrifices from the database.

Leaves metric_readings intact. Safe to run before re-seeding.

Usage:
    poetry run python scripts/clear_goals.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.milestone import Milestone
from app.models.sacrifice import Sacrifice
from app.models.goal import Goal


def main() -> None:
    db = SessionLocal()
    try:
        sacrifices = db.query(Sacrifice).delete()
        milestones = db.query(Milestone).delete()
        goals      = db.query(Goal).delete()
        db.commit()
        print(f"Deleted: {goals} goals, {milestones} milestones, {sacrifices} sacrifices")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
