"""Web frontend API — data endpoints for the three HTML views."""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.bot.intent import classify_intent
from app.core.claude_client import get_client
from app.dependencies.db import get_db
from app.models.goal import Goal, GoalState, GoalType, HabitPeriod, HabitType
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.models.milestone import Milestone, MilestoneState
from app.services.goal import (
    TERMINAL_STATES,
    activate_goal,
    create_goal,
    delete_goal as delete_goal_svc,
    get_active_perpetual_goals_by_metric,
    get_goal as get_goal_svc,
    release_goal as release_goal_svc,
    set_primacy,
    set_subordinate,
    update_goal as update_goal_svc,
)
from app.services.resource import get_resource_tension, get_three_week_view, get_willpower_pattern
from app.intelligence import memoir as memoir_intel

router = APIRouter(tags=["web"])
logger = logging.getLogger(__name__)


class CaptureRequest(BaseModel):
    text: str


class HabitLogRequest(BaseModel):
    value: float = 1.0


class GoalUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_min: Optional[float] = None
    target_max: Optional[float] = None
    weekly_target: Optional[int] = None
    target_date: Optional[date] = None


class GoalStateRequest(BaseModel):
    state: str


class GoalReleaseRequest(BaseModel):
    user_note: Optional[str] = None


class GoalCreateRequest(BaseModel):
    title: str
    goal_type: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[date] = None
    weekly_target: Optional[int] = None
    template_id: Optional[str] = None
    habit_type: Optional[str] = None
    habit_unit: Optional[str] = None
    habit_period: Optional[str] = None
    capture_keywords: Optional[list[str]] = None
    target_min: Optional[float] = None
    target_max: Optional[float] = None
    target_metric_type: Optional[str] = None


def _iso_week_bounds() -> tuple[date, date]:
    today = date.today()
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def _week_datetime_bounds() -> tuple[datetime, datetime]:
    start_date, _ = _iso_week_bounds()
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    return start_dt, start_dt + timedelta(days=7)


def _habit_count_this_week(db: Session, goal_id: int) -> int:
    start_dt, end_dt = _week_datetime_bounds()
    return (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.habit_log,
            MetricReading.text_value == str(goal_id),
            MetricReading.timestamp >= start_dt,
            MetricReading.timestamp < end_dt,
        )
        .count()
    )


def _period_bounds(period: str) -> tuple[datetime, datetime]:
    """Return (start, end) datetime bounds for the given period string."""
    now = datetime.now(timezone.utc)
    if period == "day":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, start + timedelta(days=1)
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            end = now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            end = now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, end
    # default: week
    return _week_datetime_bounds()


def _habit_accumulation(db: Session, goal_id: int, period: str = "week") -> dict:
    """Return count and value sum for habit_log readings in the current period."""
    start_dt, end_dt = _period_bounds(period)
    rows = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.habit_log,
            MetricReading.text_value == str(goal_id),
            MetricReading.timestamp >= start_dt,
            MetricReading.timestamp < end_dt,
        )
        .all()
    )
    count = len(rows)
    total = sum(r.value or 1.0 for r in rows)
    return {"count": count, "sum": round(total, 2)}


def _habit_streak(db: Session, goal_id: int) -> int:
    """Count consecutive days ending today that have at least one habit_log entry."""
    today = datetime.now(timezone.utc).date()
    streak = 0
    for days_back in range(60):
        day = today - timedelta(days=days_back)
        day_start = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = (
            db.query(MetricReading)
            .filter(
                MetricReading.metric_type == MetricType.habit_log,
                MetricReading.text_value == str(goal_id),
                MetricReading.timestamp >= day_start,
                MetricReading.timestamp < day_end,
            )
            .count()
        )
        if count > 0:
            streak += 1
        else:
            break
    return streak


def _latest_metric_value(db: Session, metric_type_str: str) -> Optional[float]:
    latest, _ = _latest_two_metric_values(db, metric_type_str)
    return latest


def _latest_two_metric_values(db: Session, metric_type_str: str) -> tuple[Optional[float], Optional[float]]:
    try:
        mt = MetricType(metric_type_str)
    except ValueError:
        return None, None
    rows = (
        db.query(MetricReading)
        .filter(MetricReading.metric_type == mt, MetricReading.value.isnot(None))
        .order_by(MetricReading.timestamp.desc())
        .limit(2)
        .all()
    )
    latest   = rows[0].value if rows else None
    previous = rows[1].value if len(rows) > 1 else None
    return latest, previous


def _trend(current: Optional[float], previous: Optional[float]) -> Optional[str]:
    if current is None or previous is None:
        return None
    if current > previous:
        return "up"
    if current < previous:
        return "down"
    return "flat"


def _rag(value: Optional[float], target_min: Optional[float], target_max: Optional[float]) -> str:
    if value is None:
        return "none"
    if target_min is not None and value < target_min:
        return "red"
    if target_max is not None and value > target_max:
        return "red"
    return "green"


def _snap(s) -> dict:
    te = s.time_envelope_hours or 1
    re = s.recovery_envelope_tss or 1
    return {
        "label": s.label,
        "week_start": str(s.week_start),
        "time_committed_hours": s.time_committed_hours,
        "time_envelope_hours": s.time_envelope_hours,
        "time_pct": round(s.time_committed_hours / te * 100, 1),
        "recovery_committed_tss": s.recovery_committed_tss,
        "recovery_envelope_tss": s.recovery_envelope_tss,
        "recovery_pct": round(s.recovery_committed_tss / re * 100, 1),
        "recovery_actual_tss": s.recovery_actual_tss,
        "attention_count": s.attention_count,
    }


# ── Now view helpers ──────────────────────────────────────────────────────────

_METRIC_UNITS: dict[str, str] = {
    "hrv": "ms",
    "sleep_score": "",
    "sleep_duration_hours": "h",
    "resting_hr": "bpm",
    "body_battery": "",
    "stress": "",
    "weight": "kg",
}

_SPORT_TYPE_MAP: dict[str, str] = {
    "run": "run", "trail run": "run", "virtual run": "run",
    "ride": "ride", "virtual ride": "ride", "gravel ride": "ride",
    "mountain bike ride": "ride", "e-bike ride": "ride",
    "swim": "swim", "open water swimming": "swim",
    "walk": "walk", "hike": "walk",
    "weight training": "strength", "workout": "strength",
    "crossfit": "strength", "yoga": "strength",
}


def _to_sport_type(activity_type: str) -> str:
    return _SPORT_TYPE_MAP.get((activity_type or "").lower(), "other")


def _today_garmin_reading(db: Session, metric_type: MetricType) -> Optional[float]:
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    row = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == metric_type,
            MetricReading.source == MetricSource.garmin,
            MetricReading.timestamp >= today_start,
            MetricReading.value.isnot(None),
        )
        .order_by(MetricReading.timestamp.desc())
        .first()
    )
    return row.value if row else None


def _reading_on_date(db: Session, metric_type: MetricType, d: date) -> Optional[float]:
    start = datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    row = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == metric_type,
            MetricReading.timestamp >= start,
            MetricReading.timestamp < end,
            MetricReading.value.isnot(None),
        )
        .order_by(MetricReading.timestamp.desc())
        .first()
    )
    return row.value if row else None


def _ninety_day_avg(db: Session, metric_type: MetricType) -> Optional[float]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    rows = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == metric_type,
            MetricReading.timestamp >= cutoff,
            MetricReading.value.isnot(None),
        )
        .all()
    )
    if not rows:
        return None
    return sum(r.value for r in rows) / len(rows)


def _compute_general_condition(
    sleep_score: Optional[float],
    body_battery: Optional[float],
    hrv: Optional[float],
    hrv_avg_90d: Optional[float],
) -> str:
    if sleep_score is None and body_battery is None and hrv is None:
        return "No data yet"
    if (sleep_score is not None and sleep_score < 50) or \
       (body_battery is not None and body_battery < 20) or \
       (hrv is not None and hrv_avg_90d is not None and hrv < hrv_avg_90d * 0.85):
        return "Depleted"
    sleep_ok   = sleep_score  is None or sleep_score  >= 65
    battery_ok = body_battery is None or body_battery >= 40
    hrv_ok     = hrv is None or hrv_avg_90d is None or hrv >= hrv_avg_90d * 0.95
    if sleep_ok and battery_ok and hrv_ok:
        return "Restored"
    return "Carrying Load"


@router.get("/")
def root_redirect():
    return RedirectResponse(url="/web/index.html")


@router.get("/v1/now")
def get_now(db: Session = Depends(get_db)):
    today = date.today()
    week_start, week_end = _iso_week_bounds()

    # Perpetual goals with RAG status
    perpetual = (
        db.query(Goal)
        .filter(Goal.goal_type == GoalType.perpetual, Goal.state.notin_(list(TERMINAL_STATES)))
        .all()
    )
    perpetual_goals = []
    for g in perpetual:
        if g.target_metric_type:
            current, previous = _latest_two_metric_values(db, g.target_metric_type)
        else:
            current, previous = None, None
        perpetual_goals.append({
            "id": g.id,
            "title": g.title,
            "state": g.state.value,
            "metric_type": g.target_metric_type,
            "current_value": current,
            "target_min": g.target_min,
            "target_max": g.target_max,
            "rag": _rag(current, g.target_min, g.target_max),
            "trend": _trend(current, previous),
        })

    # Milestones due this week or currently active
    all_milestones = (
        db.query(Milestone, Goal.title.label("goal_title"))
        .join(Goal, Milestone.goal_id == Goal.id)
        .filter(
            Goal.state.notin_(list(TERMINAL_STATES)),
            Milestone.state.in_([MilestoneState.pending, MilestoneState.active]),
        )
        .all()
    )
    this_week_milestones = []
    seen = set()
    for m, goal_title in all_milestones:
        in_week = m.target_date and week_start <= m.target_date <= week_end
        is_active = m.state == MilestoneState.active
        if (in_week or is_active) and m.id not in seen:
            this_week_milestones.append({
                "id": m.id,
                "goal_id": m.goal_id,
                "goal_title": goal_title,
                "title": m.title,
                "state": m.state.value,
                "target_date": str(m.target_date) if m.target_date else None,
            })
            seen.add(m.id)

    # Achievement goals with target dates
    deadline_goals = (
        db.query(Goal)
        .filter(Goal.target_date.isnot(None), Goal.state.notin_(list(TERMINAL_STATES)))
        .order_by(Goal.target_date.asc())
        .all()
    )
    goals_with_deadlines = []
    for g in deadline_goals:
        pending = [
            m for m in g.milestones
            if m.state in (MilestoneState.suggested, MilestoneState.pending, MilestoneState.active)
        ]
        pending.sort(key=lambda m: m.sequence)
        goals_with_deadlines.append({
            "id": g.id,
            "title": g.title,
            "state": g.state.value,
            "target_date": str(g.target_date),
            "days_remaining": (g.target_date - today).days,
            "milestone_count": len(pending),
            "next_milestone": pending[0].title if pending else None,
        })

    tension = get_resource_tension(db)
    three_week = get_three_week_view(db)

    resources_dict = {
        "time_pct": round(tension.time_ratio * 100, 1),
        "recovery_pct": round(tension.recovery_ratio * 100, 1),
        "attention_count": tension.attention_count,
        "three_week": {
            "last_week": _snap(three_week.last_week),
            "this_week": _snap(three_week.this_week),
            "next_week": _snap(three_week.next_week),
        },
    }

    # ── General condition ────────────────────────────────────────────────────
    sleep_today   = _today_garmin_reading(db, MetricType.sleep_score)
    battery_today = _today_garmin_reading(db, MetricType.body_battery)
    hrv_today     = _today_garmin_reading(db, MetricType.hrv)
    hrv_avg       = _ninety_day_avg(db, MetricType.hrv)
    general_condition = _compute_general_condition(
        sleep_today, battery_today, hrv_today, hrv_avg
    )

    # ── Health metrics (perpetual goals with readings) ───────────────────────
    health_metrics = []
    for g in perpetual:
        if not g.target_metric_type:
            continue
        try:
            mt = MetricType(g.target_metric_type)
        except ValueError:
            continue
        current, _ = _latest_two_metric_values(db, g.target_metric_type)
        if current is None:
            continue
        today_val = _reading_on_date(db, mt, today)
        yest_val  = _reading_on_date(db, mt, today - timedelta(days=1))
        health_metrics.append({
            "metric_name": g.title,
            "current_value": current,
            "target_min": g.target_min,
            "target_max": g.target_max,
            "trend": _trend(today_val, yest_val),
            "rag": _rag(current, g.target_min, g.target_max),
            "unit": _METRIC_UNITS.get(g.target_metric_type, ""),
        })

    # ── Activities this week ─────────────────────────────────────────────────
    week_start_dt, _ = _week_datetime_bounds()
    strava_acts = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.activity,
            MetricReading.source == MetricSource.strava,
            MetricReading.timestamp >= week_start_dt,
        )
        .order_by(MetricReading.timestamp.asc())
        .all()
    )
    activities_this_week = []
    for a in strava_acts:
        try:
            notes = json.loads(a.notes) if a.notes else {}
        except (json.JSONDecodeError, TypeError):
            notes = {}
        at       = notes.get("type", a.text_value or "")
        dist     = notes.get("distance_km")
        tss_val  = notes.get("tss")
        ts = a.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        activities_this_week.append({
            "sport_type":   _to_sport_type(at),
            "distance_km":  round(dist, 1) if dist is not None else None,
            "tss":          round(tss_val) if tss_val is not None else None,
            "day_name":     ts.strftime("%A"),
            "timestamp":    ts.isoformat(),
        })

    # ── Goals snapshot ───────────────────────────────────────────────────────
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)
    _tss_4wk = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.tss,
            MetricReading.source == MetricSource.strava,
            MetricReading.timestamp >= four_weeks_ago,
        )
        .all()
    )
    _act_count_4wk = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.activity,
            MetricReading.source == MetricSource.strava,
            MetricReading.timestamp >= four_weeks_ago,
        )
        .count()
    )
    _avg_tss_4wk = sum(r.value or 0 for r in _tss_4wk) / 4
    _avg_act_4wk = _act_count_4wk / 4

    def _goal_trajectory(g: Goal) -> str:
        if g.weekly_tss and _avg_tss_4wk > 0:
            pct: Optional[float] = _avg_tss_4wk / g.weekly_tss
        elif g.weekly_time_hours and _avg_act_4wk > 0:
            pct = _avg_act_4wk / max(1.0, g.weekly_time_hours / 1.5)
        elif _act_count_4wk > 0:
            pct = 1.0
        else:
            return "No data"
        if pct >= 1.1: return "Ahead"
        if pct >= 0.7: return "On track"
        return "Behind"

    all_active_goals = (
        db.query(Goal)
        .filter(Goal.state.notin_(list(TERMINAL_STATES)))
        .order_by(Goal.created_at.desc())
        .all()
    )
    goals_snapshot = []
    for g in all_active_goals:
        entry: dict = {
            "id":         g.id,
            "title":      g.title,
            "goal_type":  g.goal_type.value if g.goal_type else None,
            "state":      g.state.value,
            "is_primacy": g.state == GoalState.primacy,
        }
        if g.goal_type == GoalType.perpetual:
            c, _ = _latest_two_metric_values(db, g.target_metric_type or "")
            entry["rag"] = _rag(c, g.target_min, g.target_max)
        elif g.goal_type == GoalType.achievement:
            entry["days_remaining"] = (g.target_date - today).days if g.target_date else None
            entry["trajectory"] = _goal_trajectory(g) if g.target_date else "No data"
        elif g.goal_type == GoalType.habit:
            period     = g.habit_period.value if g.habit_period else "week"
            habit_type = g.habit_type.value if g.habit_type else "count"
            accum      = _habit_accumulation(db, g.id, period)
            if habit_type in ("duration", "volume"):
                entry["this_period_count"] = round(accum["sum"])
            else:
                entry["this_period_count"] = accum["count"]
            entry["weekly_target"] = g.weekly_target
        goals_snapshot.append(entry)

    return {
        # Preserved for backward compatibility
        "perpetual_goals":      perpetual_goals,
        "this_week_milestones": this_week_milestones,
        "goals_with_deadlines": goals_with_deadlines,
        "resources":            resources_dict,
        # New fields
        "general_condition":    general_condition,
        "health_metrics":       health_metrics,
        "activities_this_week": activities_this_week,
        "goals_snapshot":       goals_snapshot,
        "three_week_resources": resources_dict,
    }


@router.get("/v1/reflection/trajectory")
def get_trajectory(db: Session = Depends(get_db)):
    """Active achievement goals with trajectory — status, 4-week activity trend, current milestone."""
    goals = (
        db.query(Goal)
        .filter(
            Goal.state.notin_(list(TERMINAL_STATES)),
            Goal.goal_type == GoalType.achievement,
            Goal.target_date.isnot(None),
        )
        .order_by(Goal.target_date.asc())
        .all()
    )

    today = date.today()
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)

    # One query for all activities in the last 4 weeks
    all_activities = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.activity,
            MetricReading.source == MetricSource.strava,
            MetricReading.timestamp >= four_weeks_ago,
        )
        .all()
    )
    all_tss = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.tss,
            MetricReading.source == MetricSource.strava,
            MetricReading.timestamp >= four_weeks_ago,
        )
        .all()
    )

    # Build ISO week keys for the last 4 complete/current weeks
    def _week_keys() -> list[tuple[int, int]]:
        keys = []
        for w in range(3, -1, -1):
            d = today - timedelta(weeks=w)
            keys.append(d.isocalendar()[:2])
        return keys

    week_keys = _week_keys()

    def _weekly_activity_counts() -> list[int]:
        counts = {k: 0 for k in week_keys}
        for a in all_activities:
            ts = a.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            key = ts.date().isocalendar()[:2]
            if key in counts:
                counts[key] += 1
        return [counts[k] for k in week_keys]

    def _weekly_tss_totals() -> list[float]:
        totals = {k: 0.0 for k in week_keys}
        for r in all_tss:
            ts = r.timestamp
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            key = ts.date().isocalendar()[:2]
            if key in totals:
                totals[key] += r.value or 0.0
        return [totals[k] for k in week_keys]

    activity_counts = _weekly_activity_counts()
    tss_totals = _weekly_tss_totals()
    actual_activity_avg = sum(activity_counts) / 4
    actual_tss_avg = sum(tss_totals) / 4

    result = []
    for g in goals:
        days_remaining = (g.target_date - today).days

        # Status: compare actual training load to committed
        has_activity = any(v > 0 for v in activity_counts)
        if g.weekly_tss and actual_tss_avg > 0:
            pct = actual_tss_avg / g.weekly_tss
        elif g.weekly_time_hours and actual_activity_avg > 0:
            required = max(1.0, g.weekly_time_hours / 1.5)
            pct = actual_activity_avg / required
        elif has_activity:
            pct = 1.0  # activity present, no committed baseline → assume on track
        else:
            pct = None

        if pct is None:
            status = "No data"
        elif pct >= 1.1:
            status = "Ahead"
        elif pct >= 0.7:
            status = "On Track"
        else:
            status = "Behind"

        # Current milestone (first pending/active, ordered by sequence)
        pending = sorted(
            [m for m in g.milestones if m.state in (
                MilestoneState.suggested, MilestoneState.pending, MilestoneState.active
            )],
            key=lambda m: m.sequence,
        )
        ms = pending[0] if pending else None
        milestone_data = None
        if ms:
            milestone_data = {
                "id": ms.id,
                "title": ms.title,
                "state": ms.state.value,
                "current_value": ms.current_value if ms.target_value else None,
                "target_value": ms.target_value,
                "target_date": str(ms.target_date) if ms.target_date else None,
            }

        result.append({
            "id": g.id,
            "title": g.title,
            "state": g.state.value,
            "target_date": str(g.target_date),
            "days_remaining": days_remaining,
            "status": status,
            "weekly_activity_trend": activity_counts,
            "weekly_tss_trend": [round(v, 1) for v in tss_totals],
            "current_milestone": milestone_data,
        })

    return {"goals": result}


@router.get("/v1/goals/summary")
def get_goals_summary(db: Session = Depends(get_db)):
    goals = (
        db.query(Goal)
        .filter(Goal.state.notin_(list(TERMINAL_STATES)))
        .order_by(Goal.created_at.desc())
        .all()
    )
    result = []
    for g in goals:
        milestones = sorted(
            [m for m in g.milestones if m.state in (
                MilestoneState.suggested, MilestoneState.pending, MilestoneState.active
            )],
            key=lambda m: m.sequence,
        )
        entry = {
            "id": g.id,
            "title": g.title,
            "description": g.description,
            "state": g.state.value,
            "goal_type": g.goal_type.value if g.goal_type else None,
            "target_date": str(g.target_date) if g.target_date else None,
            "weekly_time_hours": g.weekly_time_hours,
            "weekly_tss": g.weekly_tss,
            "weekly_target": g.weekly_target,
            "is_primacy": g.state == GoalState.primacy,
            "is_drifting": g.state == GoalState.drifting,
            "milestones": [
                {
                    "id": m.id,
                    "title": m.title,
                    "state": m.state.value,
                    "target_date": str(m.target_date) if m.target_date else None,
                    "sequence": m.sequence,
                }
                for m in milestones
            ],
            "sacrifice_count": len(g.sacrifices),
            "created_at": g.created_at.isoformat() if g.created_at else None,
        }
        if g.goal_type == GoalType.habit:
            period = g.habit_period.value if g.habit_period else "week"
            habit_type = g.habit_type.value if g.habit_type else "count"
            accum = _habit_accumulation(db, g.id, period)
            entry["habit_type"] = habit_type
            entry["habit_unit"] = g.habit_unit or "sessions"
            entry["habit_period"] = period
            entry["this_week_count"] = _habit_count_this_week(db, g.id)  # backward compat
            entry["this_period_count"] = accum["count"]
            entry["this_period_sum"] = accum["sum"]
            if habit_type == "consistency":
                entry["streak"] = _habit_streak(db, g.id)
            entry["capture_keywords"] = json.loads(g.capture_keywords) if g.capture_keywords else []
        if g.goal_type == GoalType.perpetual:
            if g.target_metric_type:
                current, previous = _latest_two_metric_values(db, g.target_metric_type)
            else:
                current, previous = None, None
            entry["target_metric_type"] = g.target_metric_type
            entry["current_value"] = current
            entry["target_min"] = g.target_min
            entry["target_max"] = g.target_max
            entry["rag"] = _rag(current, g.target_min, g.target_max)
            entry["trend"] = _trend(current, previous)
        result.append(entry)
    return {"goals": result}


@router.get("/v1/reflection/activities")
def get_reflection_activities(db: Session = Depends(get_db)):
    """Recent Strava activities from MetricReadings, newest first, limit 20."""
    rows = (
        db.query(MetricReading)
        .filter(
            MetricReading.source == MetricSource.strava,
            MetricReading.metric_type == MetricType.activity,
        )
        .order_by(MetricReading.timestamp.desc())
        .limit(20)
        .all()
    )

    activities = []
    for r in rows:
        entry: dict = {
            "date": r.timestamp.date().isoformat(),
        }
        if r.notes:
            try:
                notes = json.loads(r.notes)
                entry["name"]       = notes.get("name")
                entry["sport_type"] = notes.get("type") or notes.get("sport_type")
                entry["distance_km"] = notes.get("distance_km")
                moving_s = notes.get("moving_time_s")
                entry["duration_min"] = round(moving_s / 60, 1) if moving_s else None
                entry["tss"]        = notes.get("tss")
            except (ValueError, TypeError):
                pass
        activities.append(entry)

    return {"activities": activities}


@router.get("/v1/reflection")
def get_reflection(db: Session = Depends(get_db)):
    def _entry(g):
        return {
            "id": g.id,
            "title": g.title,
            "description": g.description,
            "state": g.state.value,
            "memoir": g.memoir,
            "release_reason": g.release_reason,
            "closed_at": (
                (g.completed_at or g.released_at).isoformat()
                if (g.completed_at or g.released_at) else None
            ),
            "sacrifice_count": len(g.sacrifices),
        }

    completed = (
        db.query(Goal)
        .filter(Goal.state == GoalState.completed)
        .order_by(Goal.completed_at.desc())
        .all()
    )
    released = (
        db.query(Goal)
        .filter(Goal.state == GoalState.released)
        .order_by(Goal.released_at.desc())
        .all()
    )
    willpower = get_willpower_pattern(db)

    return {
        "completed": [_entry(g) for g in completed],
        "released": [_entry(g) for g in released],
        "sacrifice_pattern": {
            "sacrifice_count_28d": willpower.sacrifice_count_28d,
            "dominant_resource": willpower.dominant_resource,
            "by_resource": willpower.by_resource,
        },
    }


@router.post("/v1/goals", status_code=201)
def create_new_goal(body: GoalCreateRequest, db: Session = Depends(get_db)):
    """Create and immediately activate a new goal from the web UI."""
    if body.goal_type == "perpetual" and body.target_metric_type:
        if get_active_perpetual_goals_by_metric(db, body.target_metric_type):
            raise HTTPException(
                status_code=400,
                detail="An active goal for this metric already exists.",
            )

    goal = create_goal(
        db,
        title=body.title,
        description=body.description,
        target_date=body.target_date,
    )
    goal = activate_goal(db, goal.id)

    updates: dict = {}

    if body.goal_type:
        try:
            updates["goal_type"] = GoalType(body.goal_type)
        except ValueError:
            pass

    if body.weekly_target is not None:
        updates["weekly_target"] = body.weekly_target

    if body.template_id:
        updates["template_id"] = body.template_id

    if body.habit_type:
        try:
            updates["habit_type"] = HabitType(body.habit_type)
        except ValueError:
            pass

    if body.habit_unit:
        updates["habit_unit"] = body.habit_unit

    if body.habit_period:
        try:
            updates["habit_period"] = HabitPeriod(body.habit_period)
        except ValueError:
            pass

    if body.capture_keywords is not None:
        updates["capture_keywords"] = json.dumps(body.capture_keywords)

    if body.target_metric_type:
        updates["target_metric_type"] = body.target_metric_type
    if body.target_min is not None:
        updates["target_min"] = body.target_min
    if body.target_max is not None:
        updates["target_max"] = body.target_max

    if updates:
        for k, v in updates.items():
            setattr(goal, k, v)
        goal.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(goal)

    logger.info(f"create_new_goal: id={goal.id} title={goal.title!r} type={goal.goal_type} template={goal.template_id}")
    return {
        "id": goal.id,
        "title": goal.title,
        "state": goal.state.value,
        "goal_type": goal.goal_type.value if goal.goal_type else None,
        "template_id": goal.template_id,
    }


@router.post("/v1/goals/{goal_id}/habit/log", status_code=201)
def log_habit(
    goal_id: int,
    body: HabitLogRequest = Body(default=HabitLogRequest()),
    db: Session = Depends(get_db),
):
    """Record a habit completion for today. value=1 for count/consistency, minutes for duration, amount for volume."""
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.goal_type != GoalType.habit:
        raise HTTPException(status_code=400, detail="Goal is not a habit goal")

    reading = MetricReading(
        timestamp=datetime.now(timezone.utc),
        metric_type=MetricType.habit_log,
        text_value=str(goal_id),
        value=body.value,
        source=MetricSource.manual,
    )
    db.add(reading)
    db.commit()

    period = goal.habit_period.value if goal.habit_period else "week"
    habit_type = goal.habit_type.value if goal.habit_type else "count"
    accum = _habit_accumulation(db, goal_id, period)

    result = {
        "goal_id": goal_id,
        "this_week_count": _habit_count_this_week(db, goal_id),
        "this_period_count": accum["count"],
        "this_period_sum": accum["sum"],
        "habit_type": habit_type,
        "habit_period": period,
    }
    if habit_type == "consistency":
        result["streak"] = _habit_streak(db, goal_id)
    return result


# ── Goal management endpoints ─────────────────────────────────────────────────

@router.patch("/v1/goals/{goal_id}")
def patch_goal(goal_id: int, body: GoalUpdateRequest, db: Session = Depends(get_db)):
    """Partial update of goal fields from the web UI edit panel."""
    data = body.model_dump(exclude_unset=True)
    goal = update_goal_svc(db, goal_id, data)
    return {"id": goal.id, "title": goal.title, "state": goal.state.value}


@router.patch("/v1/goals/{goal_id}/state")
def patch_goal_state(goal_id: int, body: GoalStateRequest, db: Session = Depends(get_db)):
    """Lifecycle state transition — active, primacy, or subordinate."""
    dispatch = {
        "active":      activate_goal,
        "primacy":     set_primacy,
        "subordinate": set_subordinate,
    }
    fn = dispatch.get(body.state)
    if fn is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported state transition: {body.state!r}. Allowed: {list(dispatch)}",
        )
    goal = fn(db, goal_id)
    return {"id": goal.id, "state": goal.state.value}


@router.get("/v1/goals/{goal_id}/memoir")
def get_goal_memoir(goal_id: int, db: Session = Depends(get_db)):
    """Draft a memoir preview for a goal (used before release to show the user)."""
    goal = get_goal_svc(db, goal_id)
    client = get_client()
    text = memoir_intel.draft(goal, goal.sacrifices, goal.milestones, client)
    return {"goal_id": goal_id, "memoir": text}


@router.post("/v1/goals/{goal_id}/release")
def release_goal_endpoint(goal_id: int, body: GoalReleaseRequest, db: Session = Depends(get_db)):
    """Release a goal. Generates a memoir draft and stores it alongside the user's note."""
    goal = get_goal_svc(db, goal_id)
    client = get_client()
    memoir_text = memoir_intel.draft(goal, goal.sacrifices, goal.milestones, client)
    goal = release_goal_svc(db, goal_id, reason=body.user_note or None, memoir=memoir_text)
    return {"id": goal.id, "state": goal.state.value}


@router.delete("/v1/goals/{goal_id}", status_code=204)
def delete_goal_endpoint(goal_id: int, db: Session = Depends(get_db)):
    """Permanently delete a goal. Blocked if the goal has sacrifice history or achieved milestones."""
    goal = get_goal_svc(db, goal_id)
    has_activity = bool(goal.sacrifices) or any(
        m.state in (MilestoneState.achieved, MilestoneState.missed) for m in goal.milestones
    )
    if has_activity:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a goal with activity history. Release it instead.",
        )
    delete_goal_svc(db, goal_id)


# ── Template endpoints ─────────────────────────────────────────────────────────

@router.get("/v1/templates")
def get_templates():
    """Return all goal templates grouped by category."""
    from app.services.template import list_templates_by_category
    return {"categories": list_templates_by_category()}


@router.post("/v1/templates/{template_id}/preview")
def preview_template(template_id: str, db: Session = Depends(get_db)):
    """Return suggested target range or capability baseline for a template."""
    from app.services.template import get_template, suggest_target_range
    template = get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {
        "template_id": template_id,
        "goal_type": template.get("goal_type"),
        "capability_fields": template.get("capability_fields", []),
        "milestone_phases": template.get("milestone_phases", []),
        **suggest_target_range(template, db),
    }


@router.get("/v1/health/integrations")
def get_integrations_status():
    """Return last sync time and RAG status for Garmin and Strava.

    Reads Redis keys written by the ingestion jobs. Returns 'never' when
    Redis is disabled or no sync has run yet.
    """
    from app.core.redis_client import cache_get

    def _status(key: str) -> dict:
        raw = cache_get(key)
        if not raw:
            return {"last_sync": None, "status": "never"}
        try:
            last_sync = datetime.fromisoformat(raw)
        except ValueError:
            return {"last_sync": raw, "status": "never"}
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - last_sync).total_seconds() / 3600
        if age_hours <= 6:
            status = "green"
        elif age_hours <= 24:
            status = "amber"
        else:
            status = "red"
        return {"last_sync": last_sync.isoformat(), "status": status}

    return {
        "garmin": _status("sync:garmin:last_success"),
        "strava": _status("sync:strava:last_success"),
    }


@router.get("/v1/connectors/status")
def get_connectors_status(db: Session = Depends(get_db)):
    """Return full connector status: sync health, record counts, and attempt log."""
    from app.config import get_settings
    from app.core.redis_client import cache_get, get_sync_log

    settings = get_settings()

    def _sync_status(key: str) -> dict:
        raw = cache_get(key)
        if not raw:
            return {"last_sync": None, "status": "never"}
        try:
            last_sync = datetime.fromisoformat(raw)
        except ValueError:
            return {"last_sync": raw, "status": "never"}
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - last_sync).total_seconds() / 3600
        if age_hours <= 6:
            status = "green"
        elif age_hours <= 24:
            status = "amber"
        else:
            status = "red"
        return {"last_sync": last_sync.isoformat(), "status": status}

    def _record_count(source: MetricSource) -> int:
        return db.query(MetricReading).filter(MetricReading.source == source).count()

    garmin_sync = _sync_status("sync:garmin:last_success")
    strava_sync = _sync_status("sync:strava:last_success")

    return {
        "garmin": {
            "enabled": settings.garmin_enabled,
            "last_sync": garmin_sync["last_sync"],
            "status": garmin_sync["status"],
            "record_count": _record_count(MetricSource.garmin),
            "log": get_sync_log("garmin"),
        },
        "strava": {
            "enabled": settings.strava_enabled,
            "last_sync": strava_sync["last_sync"],
            "status": strava_sync["status"],
            "record_count": _record_count(MetricSource.strava),
            "log": get_sync_log("strava"),
        },
        "record_counts": {
            "garmin": _record_count(MetricSource.garmin),
            "strava": _record_count(MetricSource.strava),
            "manual": _record_count(MetricSource.manual),
            "telegram": _record_count(MetricSource.telegram),
        },
    }


_SCHEDULE_JOB_IDS = [
    "garmin_poll",
    "garmin_backstop_0730",
    "garmin_backstop",
    "strava_poll",
]


@router.get("/v1/connectors/schedule")
def get_connectors_schedule(request: Request):
    """Return next scheduled run time for each ingestion job."""
    scheduler = getattr(request.app.state, "scheduler", None)
    result = {}
    for job_id in _SCHEDULE_JOB_IDS:
        next_run = None
        if scheduler is not None:
            job = scheduler.get_job(job_id)
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        result[job_id] = {"next_run": next_run}
    return result


@router.post("/v1/admin/sync/garmin")
def trigger_garmin_sync(db: Session = Depends(get_db)):
    """Manually trigger a Garmin sync. Calls the same function as the scheduled job."""
    from app.ingestion.garmin import sync_garmin
    from app.core.redis_client import cache_get

    try:
        rows = sync_garmin(db)
        logger.info(f"Manual Garmin sync: {len(rows)} records")
        last_sync = cache_get("sync:garmin:last_success")
        if not last_sync and rows:
            last_sync = datetime.now(timezone.utc).isoformat()
        return {"status": "ok", "records_synced": len(rows), "last_sync": last_sync}
    except Exception as exc:
        logger.error(f"Manual Garmin sync failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/v1/admin/sync/strava")
def trigger_strava_sync(db: Session = Depends(get_db)):
    """Manually trigger a Strava sync. Calls the same function as the scheduled job."""
    from app.ingestion.strava import sync_strava, activity_dict_from_rows
    from app.core.redis_client import cache_get
    from app.services.milestone_progress import process_activity
    from app.bot.outreach import dispatch_milestone_notifications

    try:
        rows = sync_strava(db)
        logger.info(f"Manual Strava sync: {len(rows)} records")
        last_sync = cache_get("sync:strava:last_success")
        if not last_sync and rows:
            last_sync = datetime.now(timezone.utc).isoformat()

        all_updates = []
        for activity in activity_dict_from_rows(rows):
            try:
                updates = process_activity(db, activity)
                all_updates.extend(updates)
            except Exception as exc:
                logger.error(f"Manual Strava sync: milestone progress failed: {exc}", exc_info=True)
        if all_updates:
            logger.info(f"Manual Strava sync: {len(all_updates)} milestone update(s)")
            dispatch_milestone_notifications(all_updates)

        return {"status": "ok", "records_synced": len(rows), "last_sync": last_sync}
    except Exception as exc:
        logger.error(f"Manual Strava sync failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/v1/capture")
def capture(body: CaptureRequest, db: Session = Depends(get_db)):
    text = body.text.strip()
    if not text:
        return {"intent": None, "acknowledged": False, "response": "Nothing to capture."}

    is_morning = datetime.now(timezone.utc).hour < 10
    client = get_client()
    intent = classify_intent(text, is_morning, client)

    logger.info(f"web capture: intent={intent} text={text[:60]!r}")
    return {
        "intent": intent,
        "acknowledged": True,
        "response": f"Logged as {intent.replace('_', ' ')}.",
    }
