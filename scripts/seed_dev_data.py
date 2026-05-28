#!/usr/bin/env python
"""Seed realistic development data for planA.

Creates 3-4 goals covering different types and lifecycle states, plus sample
milestones and metric readings. Safe to run multiple times — skips any goal
whose title already exists.

Usage:
    poetry run python scripts/seed_dev_data.py
"""

import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.models.milestone import Milestone, MilestoneState, ProgressMetric, ProgressPeriod, ProgressType
from app.services.goal import (
    activate_goal,
    create_goal,
    set_primacy,
    set_subordinate,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return date.today()


def _exists(db, title: str) -> bool:
    return db.query(Goal).filter(Goal.title == title).first() is not None


def _add_milestone(db, goal_id: int, title: str, description: str,
                   sequence: int, weeks_out: int,
                   state: MilestoneState = MilestoneState.pending,
                   activity_type: str | None = None,
                   progress_type: ProgressType | None = None,
                   metric: ProgressMetric | None = None,
                   target_value: float | None = None,
                   period: ProgressPeriod | None = None) -> Milestone:
    target = _today() + timedelta(weeks=weeks_out)
    m = Milestone(
        goal_id=goal_id,
        title=title,
        description=description,
        state=state,
        sequence=sequence,
        target_date=target,
        created_at=_now(),
        updated_at=_now(),
        activity_type=activity_type,
        progress_type=progress_type,
        metric=metric,
        target_value=target_value,
        period=period,
    )
    db.add(m)
    db.commit()
    return m


def _add_metric(db, metric_type: MetricType, value: float, days_ago: int) -> None:
    ts = _now() - timedelta(days=days_ago)
    r = MetricReading(
        timestamp=ts,
        metric_type=metric_type,
        value=value,
        source=MetricSource.garmin,
    )
    db.add(r)
    db.commit()


def seed_goals(db) -> None:
    # ── 1. Half marathon — primacy, achievement ────────────────────────────────

    HALF_MARATHON = "Run a sub-2:00 half marathon"
    if not _exists(db, HALF_MARATHON):
        g = create_goal(
            db,
            title=HALF_MARATHON,
            description="Target race: Valencia Half, November. Current long run ~14km at 5:50/km. "
                        "Need to build to 18km long run and drop pace to 5:30/km.",
            target_date=_today() + timedelta(days=168),
            weekly_time_hours=6.0,
            weekly_tss=220.0,
        )
        g = activate_goal(db, g.id)
        g.goal_type = GoalType.achievement
        db.commit()
        g = set_primacy(db, g.id)

        _add_milestone(db, g.id,
            "Build weekly volume to 45km",
            "Four weeks of consistent training — three runs plus a long run.",
            sequence=1, weeks_out=6, state=MilestoneState.suggested,
            activity_type="run",
            progress_type=ProgressType.cumulative,
            metric=ProgressMetric.distance_km,
            target_value=45.0,
            period=ProgressPeriod.week)
        _add_milestone(db, g.id,
            "Complete 18km long run",
            "Long run at target half-marathon effort (5:35/km). Confidence check.",
            sequence=2, weeks_out=12,
            activity_type="run",
            progress_type=ProgressType.single_effort,
            metric=ProgressMetric.distance_km,
            target_value=18.0,
            period=ProgressPeriod.lifetime)
        _add_milestone(db, g.id,
            "Race day: Valencia Half Marathon",
            "Sub-2:00 finish. Splits: 5:40/km for first 10km, 5:30/km for last 11km.",
            sequence=3, weeks_out=24)

        print(f"  Created: {HALF_MARATHON} (primacy)")
    else:
        print(f"  Skipped: {HALF_MARATHON} (already exists)")

    # ── 2. Sleep quality — active, perpetual ──────────────────────────────────

    SLEEP = "Maintain sleep quality"
    if not _exists(db, SLEEP):
        g = create_goal(
            db,
            title=SLEEP,
            description="Garmin sleep score 75+ most nights. Bedtime before 23:00, "
                        "no alcohol within 3 hours of sleep.",
        )
        g = activate_goal(db, g.id)
        g.goal_type = GoalType.perpetual
        g.target_metric_type = MetricType.sleep_score.value
        g.target_min = 72.0
        g.target_max = 100.0
        db.commit()
        print(f"  Created: {SLEEP} (active, perpetual)")
    else:
        print(f"  Skipped: {SLEEP} (already exists)")

    # ── 3. Cook at home — subordinate, habit ─────────────────────────────────

    COOK = "Cook at home 5 times a week"
    if not _exists(db, COOK):
        g = create_goal(
            db,
            title=COOK,
            description="Time with family, control over nutrition, save money. "
                        "Counts anything cooked from ingredients — not reheating.",
            weekly_time_hours=4.0,
        )
        g = activate_goal(db, g.id)
        g.goal_type = GoalType.habit
        g.weekly_target = 5
        db.commit()
        g = set_subordinate(db, g.id)
        print(f"  Created: {COOK} (subordinate, habit, target=5/week)")
    else:
        print(f"  Skipped: {COOK} (already exists)")

    # ── 4. Read more books — active, achievement ──────────────────────────────

    READ = "Read 12 books in 2026"
    if not _exists(db, READ):
        g = create_goal(
            db,
            title=READ,
            description="One book per month. Mix of non-fiction and fiction. "
                        "Currently on book 3.",
            target_date=date(2026, 12, 31),
            weekly_time_hours=2.5,
        )
        g = activate_goal(db, g.id)
        g.goal_type = GoalType.achievement
        db.commit()

        _add_milestone(db, g.id,
            "Finish first 4 books",
            "Books 1–4 read and noted. On track for one-per-month cadence.",
            sequence=1, weeks_out=4)
        _add_milestone(db, g.id,
            "Halfway: 6 books complete",
            "End of June checkpoint.",
            sequence=2, weeks_out=18)
        _add_milestone(db, g.id,
            "12 books done",
            "Year complete.",
            sequence=3, weeks_out=32)

        print(f"  Created: {READ} (active, achievement)")
    else:
        print(f"  Skipped: {READ} (already exists)")


def seed_metric_readings(db) -> None:
    # Skip if we already have a reasonable number of readings
    existing = db.query(MetricReading).filter(
        MetricReading.source == MetricSource.garmin
    ).count()
    if existing >= 28:
        print(f"  Skipped metric readings ({existing} garmin readings already present)")
        return

    rng = random.Random(42)

    # HRV over last 14 days (realistic range ~45–65ms, slight upward trend)
    for days_ago in range(14, 0, -1):
        base = 52 + (14 - days_ago) * 0.4          # gentle upward trend
        value = round(base + rng.uniform(-4, 4), 1)
        _add_metric(db, MetricType.hrv, value, days_ago)

    # Sleep score over last 14 days (72–88)
    for days_ago in range(14, 0, -1):
        value = round(rng.uniform(72, 88), 0)
        _add_metric(db, MetricType.sleep_score, value, days_ago)

    print(f"  Created 28 metric readings (HRV + sleep score, 14 days)")


def main() -> None:
    db = SessionLocal()
    try:
        print("Seeding goals…")
        seed_goals(db)
        print("Seeding metric readings…")
        seed_metric_readings(db)
        print("Done.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
