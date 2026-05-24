"""Drift detection for perpetual goals.

A perpetual goal has a target metric range (e.g. weight 70–75 kg, HRV ≥ 55).
Drift is declared when the metric is outside range for 3+ consecutive days with
no gap in readings. A gap breaks the streak.

Conditions that suppress detection:
  - Goal already in Drifting state (already surfaced)
  - Goal is in recovery mode (is_recovering=True — accepted deviation)
  - Goal in terminal or draft state
  - Goal has no target_metric_type configured
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading
from app.services.goal import TERMINAL_STATES

DRIFT_THRESHOLD_DAYS = 3
LOOKBACK_DAYS = 7

_SKIP_STATES = TERMINAL_STATES | {GoalState.drifting, GoalState.draft}


@dataclass
class DriftEvent:
    goal_id: int
    goal_title: str
    metric_type: str
    days_outside_range: int
    current_value: Optional[float]
    target_min: Optional[float]
    target_max: Optional[float]


def _is_outside_range(
    value: float,
    target_min: Optional[float],
    target_max: Optional[float],
) -> bool:
    if target_min is not None and value < target_min:
        return True
    if target_max is not None and value > target_max:
        return True
    return False


def _count_consecutive_outside(
    readings_by_date: dict[date, float],
    target_min: Optional[float],
    target_max: Optional[float],
    reference_date: date,
    lookback_days: int = LOOKBACK_DAYS,
) -> tuple[int, Optional[float]]:
    """Count consecutive days from reference_date backwards that are outside range.

    A missing day breaks the streak — we only count unbroken runs of out-of-range
    readings. Returns (consecutive_count, most_recent_value).
    """
    consecutive = 0
    current_value: Optional[float] = None

    for offset in range(lookback_days):
        d = reference_date - timedelta(days=offset)
        if d not in readings_by_date:
            break
        value = readings_by_date[d]
        if current_value is None:
            current_value = value
        if _is_outside_range(value, target_min, target_max):
            consecutive += 1
        else:
            break

    return consecutive, current_value


def detect_drift(db: Session) -> list[DriftEvent]:
    """Return DriftEvents for perpetual goals outside their range for 3+ consecutive days."""
    goals = (
        db.query(Goal)
        .filter(
            Goal.goal_type == GoalType.perpetual,
            Goal.state.notin_(list(_SKIP_STATES)),
            Goal.target_metric_type.isnot(None),
            Goal.is_recovering == False,  # noqa: E712 — SQLAlchemy requires ==
        )
        .all()
    )

    if not goals:
        return []

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=LOOKBACK_DAYS)
    today = now.date()
    events: list[DriftEvent] = []

    for goal in goals:
        readings = (
            db.query(MetricReading)
            .filter(
                MetricReading.metric_type == goal.target_metric_type,
                MetricReading.timestamp >= cutoff,
                MetricReading.value.isnot(None),
            )
            .order_by(MetricReading.timestamp.desc())
            .all()
        )

        # One reading per calendar day — most recent wins (already ordered desc)
        readings_by_date: dict[date, float] = {}
        for r in readings:
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            d = ts.date()
            if d not in readings_by_date:
                readings_by_date[d] = r.value  # type: ignore[assignment]

        consecutive, current_value = _count_consecutive_outside(
            readings_by_date, goal.target_min, goal.target_max, today
        )

        if consecutive >= DRIFT_THRESHOLD_DAYS:
            events.append(
                DriftEvent(
                    goal_id=goal.id,
                    goal_title=goal.title,
                    metric_type=goal.target_metric_type,
                    days_outside_range=consecutive,
                    current_value=current_value,
                    target_min=goal.target_min,
                    target_max=goal.target_max,
                )
            )

    return events
