"""Fade detection for achievement goals.

Fade is declared when an achievement goal has had no milestone activity and
no Telegram captures for 14+ consecutive days. This surfaces goals that have
quietly dropped off the user's radar.

Conditions that suppress detection:
  - Goal in Draft state (not yet active)
  - Goal in terminal state (released / completed)
  - Goal is perpetual (perpetual goals drift, they don't fade)
  - Goal created less than FADE_DAYS ago (too new to fade)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading, MetricSource
from app.models.milestone import Milestone
from app.services.goal import TERMINAL_STATES

FADE_DAYS = 14

_SKIP_STATES = TERMINAL_STATES | {GoalState.draft}


@dataclass
class FadeEvent:
    goal_id: int
    goal_title: str
    days_since_activity: int
    last_activity_at: Optional[datetime]


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def detect_fade(db: Session) -> list[FadeEvent]:
    """Return FadeEvents for achievement goals with no activity for 14+ days."""
    goals = (
        db.query(Goal)
        .filter(
            Goal.state.notin_(list(_SKIP_STATES)),
            or_(Goal.goal_type == GoalType.achievement, Goal.goal_type.is_(None)),
        )
        .all()
    )

    if not goals:
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=FADE_DAYS)
    events: list[FadeEvent] = []

    for goal in goals:
        # Skip goals created less than FADE_DAYS ago — too new to declare faded
        if goal.created_at and _ensure_tz(goal.created_at) > cutoff:
            continue

        # Most recently updated milestone for this goal
        last_milestone = (
            db.query(Milestone)
            .filter(Milestone.goal_id == goal.id)
            .order_by(Milestone.updated_at.desc())
            .first()
        )

        # Most recent Telegram capture (global — any engagement counts)
        last_telegram = (
            db.query(MetricReading)
            .filter(MetricReading.source == MetricSource.telegram)
            .order_by(MetricReading.timestamp.desc())
            .first()
        )

        candidates: list[datetime] = []
        if last_milestone and last_milestone.updated_at:
            candidates.append(_ensure_tz(last_milestone.updated_at))
        if last_telegram:
            candidates.append(_ensure_tz(last_telegram.timestamp))

        if not candidates:
            events.append(
                FadeEvent(
                    goal_id=goal.id,
                    goal_title=goal.title,
                    days_since_activity=FADE_DAYS,
                    last_activity_at=None,
                )
            )
        else:
            last_activity = max(candidates)
            if last_activity < cutoff:
                days = int((now - last_activity).total_seconds() / 86400)
                events.append(
                    FadeEvent(
                        goal_id=goal.id,
                        goal_title=goal.title,
                        days_since_activity=days,
                        last_activity_at=last_activity,
                    )
                )

    return events
