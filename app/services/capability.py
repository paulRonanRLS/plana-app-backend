"""Capability baseline derivation from Strava activity history.

Reads the last 90 days of activity MetricReadings to produce a snapshot of the
user's current physical capability. Used by milestone generation so that
suggested milestones start from where the user actually is, not a generic
template.

Activity type inference is intentionally simple keyword matching on goal
title/description — no LLM needed here.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.metric_reading import MetricReading, MetricSource, MetricType

logger = logging.getLogger(__name__)

BASELINE_DAYS = 90
LONG_RUN_WINDOW_DAYS = 28   # only look at last 4 weeks for "current" long run

# Word-boundary patterns — avoids "5kg" matching "5k", "triathlete" matching "ride", etc.
_RUN_RE = re.compile(r"\b(?:run|running|ran|marathon|trail|half.marathon)\b|\b5k\b|\b10k\b", re.IGNORECASE)
_RIDE_RE = re.compile(r"\b(?:ride|cycling|bike|bicycle|triathlon|ftp|velodrome)\b", re.IGNORECASE)


@dataclass
class CapabilityBaseline:
    goal_type: str  # "run" | "ride" | "general"
    # Running
    long_run_km: Optional[float] = None
    weekly_volume_km: Optional[float] = None
    avg_pace_min_per_km: Optional[float] = None
    run_count: int = 0
    # Cycling
    ftp_estimate_w: Optional[float] = None
    longest_ride_km: Optional[float] = None
    weekly_tss: Optional[float] = None
    ride_count: int = 0


def infer_goal_activity_type(goal) -> str:
    """Return 'run', 'ride', or 'general' from the goal's title and description."""
    text = f"{goal.title or ''} {goal.description or ''}"
    if _RUN_RE.search(text):
        return "run"
    if _RIDE_RE.search(text):
        return "ride"
    return "general"


def get_capability_baseline(db: Session, goal_type: str) -> CapabilityBaseline:
    """Derive current capability from the last 90 days of Strava activity data.

    Returns a CapabilityBaseline populated with whatever metrics are available.
    All numeric fields are None if there is insufficient data.
    """
    baseline = CapabilityBaseline(goal_type=goal_type)

    if goal_type == "general":
        return baseline

    cutoff = datetime.now(timezone.utc) - timedelta(days=BASELINE_DAYS)
    recent_cutoff = datetime.now(timezone.utc) - timedelta(days=LONG_RUN_WINDOW_DAYS)

    # Fetch activity readings for the relevant sport type
    sport_filter = "run" if goal_type == "run" else "ride"
    readings = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.activity,
            MetricReading.timestamp >= cutoff,
            MetricReading.text_value.ilike(f"%{sport_filter}%"),
        )
        .order_by(MetricReading.timestamp.desc())
        .all()
    )

    if not readings:
        return baseline

    activities = []
    for r in readings:
        try:
            notes = json.loads(r.notes) if r.notes else {}
        except (ValueError, TypeError):
            notes = {}
        activities.append({
            "timestamp": r.timestamp,
            "distance_km": notes.get("distance_km") or (r.value or 0.0),
            "moving_time_s": notes.get("moving_time_s") or 0,
            "normalized_power_w": notes.get("normalized_power_w"),
        })

    if goal_type == "run":
        baseline = _run_baseline(baseline, activities, recent_cutoff)
    else:
        baseline = _ride_baseline(db, baseline, activities, cutoff)

    return baseline


def _run_baseline(
    baseline: CapabilityBaseline,
    activities: list[dict],
    recent_cutoff: datetime,
) -> CapabilityBaseline:
    baseline.run_count = len(activities)

    distances = [a["distance_km"] for a in activities if a["distance_km"]]
    if not distances:
        return baseline

    # Long run: max distance in the most recent LONG_RUN_WINDOW_DAYS
    recent = [a for a in activities if _ensure_tz(a["timestamp"]) >= recent_cutoff]
    recent_distances = [a["distance_km"] for a in recent if a["distance_km"]]
    if recent_distances:
        baseline.long_run_km = round(max(recent_distances), 1)

    # Weekly volume: total distance / (BASELINE_DAYS / 7)
    weeks = BASELINE_DAYS / 7
    baseline.weekly_volume_km = round(sum(distances) / weeks, 1)

    # Average pace: weighted by distance
    total_km = sum(a["distance_km"] for a in activities if a["distance_km"] and a["moving_time_s"])
    total_s = sum(a["moving_time_s"] for a in activities if a["distance_km"] and a["moving_time_s"])
    if total_km > 0 and total_s > 0:
        baseline.avg_pace_min_per_km = round((total_s / 60) / total_km, 2)

    return baseline


def _ride_baseline(
    db: Session,
    baseline: CapabilityBaseline,
    activities: list[dict],
    cutoff: datetime,
) -> CapabilityBaseline:
    baseline.ride_count = len(activities)

    distances = [a["distance_km"] for a in activities if a["distance_km"]]
    if distances:
        baseline.longest_ride_km = round(max(distances), 1)

    # FTP estimate: 95% of max normalised power across all rides
    powers = [
        a["normalized_power_w"]
        for a in activities
        if a.get("normalized_power_w") is not None and a["normalized_power_w"] > 0
    ]
    if powers:
        baseline.ftp_estimate_w = round(max(powers) * 0.95, 0)

    # Weekly TSS from the tss MetricType (Strava-sourced)
    tss_readings = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.tss,
            MetricReading.source == MetricSource.strava,
            MetricReading.timestamp >= cutoff,
            MetricReading.value.isnot(None),
        )
        .all()
    )
    if tss_readings:
        total_tss = sum(r.value for r in tss_readings if r.value)
        weeks = BASELINE_DAYS / 7
        baseline.weekly_tss = round(total_tss / weeks, 1)

    return baseline


def _ensure_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
