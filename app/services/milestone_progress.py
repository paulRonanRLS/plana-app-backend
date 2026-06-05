"""Milestone progress tracking from Strava activities.

process_activity(db, activity) is the main entry point. It accepts the
canonical activity dict produced by app/ingestion/strava.py and updates
all relevant milestones for active goals.

Return value: list of ProgressUpdate describing every milestone that changed.
Callers use these to build Telegram notifications.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.milestone import Milestone, MilestoneState, ProgressMetric, ProgressPeriod, ProgressType
from app.models.goal import Goal
from app.services.goal import TERMINAL_STATES

logger = logging.getLogger(__name__)

# Strava sport_type values (title-case) → normalised lowercase for matching
_STRAVA_TYPE_MAP: dict[str, str] = {
    "run": "run",
    "ride": "ride",
    "swim": "swim",
    "walk": "walk",
    "hike": "walk",
    "virtualrun": "run",
    "virtualride": "ride",
}


@dataclass
class ProgressUpdate:
    milestone_id: int
    milestone_title: str
    goal_title: str
    activity_type: str       # normalised lowercase
    metric_value: float      # value extracted from this activity
    metric: str              # distance_km / duration_min / tss / count
    current_value: float     # milestone current_value after update
    target_value: float
    period: str              # week / month / lifetime
    achieved: bool


def _normalise_activity_type(raw: str) -> str:
    """Map Strava sport_type to a normalised lowercase string."""
    return _STRAVA_TYPE_MAP.get(raw.lower(), raw.lower())


def _activity_matches_milestone(normalised_type: str, milestone_activity_type: str | None) -> bool:
    if not milestone_activity_type:
        return False
    mt = milestone_activity_type.lower()
    return mt == "any" or mt == normalised_type


def _extract_metric_value(activity: dict, metric: ProgressMetric) -> float | None:
    """Pull the relevant number from the activity dict."""
    if metric == ProgressMetric.distance_km:
        return activity.get("distance_km")
    if metric == ProgressMetric.duration_min:
        moving_s = activity.get("moving_time_s")
        return round(moving_s / 60, 2) if moving_s is not None else None
    if metric == ProgressMetric.pace_per_km:
        return activity.get("pace_per_km")
    if metric == ProgressMetric.tss:
        return activity.get("tss")
    if metric == ProgressMetric.count:
        return 1.0
    return None


def _period_has_reset(milestone: Milestone, activity_ts: datetime) -> bool:
    """Return True if the milestone's accumulation period has rolled over."""
    if milestone.period == ProgressPeriod.lifetime:
        return False

    last_update = milestone.updated_at
    if last_update is None:
        return False
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=timezone.utc)
    if activity_ts.tzinfo is None:
        activity_ts = activity_ts.replace(tzinfo=timezone.utc)

    if milestone.period == ProgressPeriod.week:
        # ISO week: Monday is day 0
        def _week_start(dt: datetime) -> datetime:
            return dt.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - __import__("datetime").timedelta(days=dt.weekday())

        return _week_start(activity_ts) > _week_start(last_update)

    if milestone.period == ProgressPeriod.month:
        return (activity_ts.year, activity_ts.month) > (last_update.year, last_update.month)

    return False


def process_activity(db: Session, activity: dict) -> list[ProgressUpdate]:
    """Update all active milestones that track this activity type.

    Returns a ProgressUpdate for every milestone whose current_value changed.
    """
    raw_type = activity.get("activity_type", "")
    normalised_type = _normalise_activity_type(raw_type)

    activity_ts = activity.get("timestamp")
    if activity_ts is None:
        activity_ts = datetime.now(timezone.utc)
    if isinstance(activity_ts, datetime) and activity_ts.tzinfo is None:
        activity_ts = activity_ts.replace(tzinfo=timezone.utc)

    # All milestones for non-terminal goals that have progress tracking configured
    milestones = (
        db.query(Milestone, Goal.title.label("goal_title"))
        .join(Goal, Milestone.goal_id == Goal.id)
        .filter(
            Goal.state.notin_(list(TERMINAL_STATES)),
            Milestone.state.in_([MilestoneState.pending, MilestoneState.active]),
            Milestone.progress_type.isnot(None),
            Milestone.metric.isnot(None),
            Milestone.target_value.isnot(None),
        )
        .all()
    )

    updates: list[ProgressUpdate] = []

    for milestone, goal_title in milestones:
        if not _activity_matches_milestone(normalised_type, milestone.activity_type):
            continue

        metric_value = _extract_metric_value(activity, milestone.metric)
        if metric_value is None:
            logger.debug(f"Milestone {milestone.id}: metric {milestone.metric} not available in activity — skipping")
            continue

        # Period reset for cumulative milestones
        if milestone.progress_type == ProgressType.cumulative:
            if _period_has_reset(milestone, activity_ts):
                logger.info(f"Milestone {milestone.id} ({milestone.title!r}): period reset")
                milestone.current_value = 0.0

            milestone.current_value = round(milestone.current_value + metric_value, 3)
            achieved = milestone.current_value >= milestone.target_value

        else:  # single_effort
            if milestone.metric == ProgressMetric.pace_per_km:
                # Pace comparison is inverted — lower value means faster pace.
                # current_value stores the best (lowest) pace seen; 0.0 means no data yet.
                if milestone.current_value == 0.0 or metric_value < milestone.current_value:
                    milestone.current_value = round(metric_value, 3)
                achieved = metric_value <= milestone.target_value
            else:
                # Track the best single-activity value seen
                if metric_value > milestone.current_value:
                    milestone.current_value = round(metric_value, 3)
                achieved = metric_value >= milestone.target_value

        if achieved and milestone.state != MilestoneState.achieved:
            milestone.state = MilestoneState.achieved
            milestone.achieved_at = datetime.now(timezone.utc)
            logger.info(
                f"Milestone {milestone.id} ({milestone.title!r}) achieved — "
                f"{milestone.metric.value}={milestone.current_value} >= {milestone.target_value}"
            )

        milestone.updated_at = datetime.now(timezone.utc)
        db.add(milestone)

        updates.append(ProgressUpdate(
            milestone_id=milestone.id,
            milestone_title=milestone.title,
            goal_title=goal_title,
            activity_type=normalised_type,
            metric_value=metric_value,
            metric=milestone.metric.value,
            current_value=milestone.current_value,
            target_value=milestone.target_value,
            period=milestone.period.value,
            achieved=achieved,
        ))

    if updates:
        db.commit()

    return updates


def activity_dict_from_row(row) -> dict:
    """Convert a MetricReading activity row back to a dict for process_activity.

    The row is a MetricReading with metric_type=activity and notes JSON.
    """
    import json

    try:
        notes = json.loads(row.notes) if row.notes else {}
    except (ValueError, TypeError):
        notes = {}

    return {
        "activity_type": notes.get("type") or row.text_value or "",
        "distance_km": notes.get("distance_km") or row.value,
        "moving_time_s": notes.get("moving_time_s"),
        "pace_per_km": notes.get("pace_per_km"),
        "tss": notes.get("tss"),
        "timestamp": row.timestamp,
    }
