"""Web frontend API — data endpoints for the three HTML views."""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.bot.intent import classify_intent
from app.core.claude_client import get_client
from app.dependencies.db import get_db
from fastapi import HTTPException
from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.models.milestone import Milestone, MilestoneState
from app.services.goal import TERMINAL_STATES, activate_goal, create_goal
from app.services.resource import get_resource_tension, get_three_week_view, get_willpower_pattern

router = APIRouter(tags=["web"])
logger = logging.getLogger(__name__)


class CaptureRequest(BaseModel):
    text: str


class GoalCreateRequest(BaseModel):
    title: str
    goal_type: Optional[str] = None   # "achievement" | "perpetual" | "habit"
    description: Optional[str] = None
    target_date: Optional[date] = None
    weekly_target: Optional[int] = None   # habit goals only


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


def _latest_metric_value(db: Session, metric_type_str: str) -> Optional[float]:
    try:
        mt = MetricType(metric_type_str)
    except ValueError:
        return None
    r = (
        db.query(MetricReading)
        .filter(MetricReading.metric_type == mt, MetricReading.value.isnot(None))
        .order_by(MetricReading.timestamp.desc())
        .first()
    )
    return r.value if r else None


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
        current = _latest_metric_value(db, g.target_metric_type) if g.target_metric_type else None
        perpetual_goals.append({
            "id": g.id,
            "title": g.title,
            "state": g.state.value,
            "metric_type": g.target_metric_type,
            "current_value": current,
            "target_min": g.target_min,
            "target_max": g.target_max,
            "rag": _rag(current, g.target_min, g.target_max),
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
    te = tension.time_envelope_hours or 1
    re = tension.recovery_envelope_tss or 1

    return {
        "perpetual_goals": perpetual_goals,
        "this_week_milestones": this_week_milestones,
        "goals_with_deadlines": goals_with_deadlines,
        "resources": {
            "time_pct": round(tension.time_ratio * 100, 1),
            "recovery_pct": round(tension.recovery_ratio * 100, 1),
            "attention_count": tension.attention_count,
            "three_week": {
                "last_week": _snap(three_week.last_week),
                "this_week": _snap(three_week.this_week),
                "next_week": _snap(three_week.next_week),
            },
        },
    }


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
            entry["this_week_count"] = _habit_count_this_week(db, g.id)
        if g.goal_type == GoalType.perpetual:
            current = _latest_metric_value(db, g.target_metric_type) if g.target_metric_type else None
            entry["current_value"] = current
            entry["target_min"] = g.target_min
            entry["target_max"] = g.target_max
            entry["rag"] = _rag(current, g.target_min, g.target_max)
        result.append(entry)
    return {"goals": result}


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
    goal = create_goal(
        db,
        title=body.title,
        description=body.description,
        target_date=body.target_date,
    )
    goal = activate_goal(db, goal.id)

    if body.goal_type:
        try:
            goal.goal_type = GoalType(body.goal_type)
            goal.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(goal)
        except ValueError:
            pass

    if body.weekly_target is not None:
        goal.weekly_target = body.weekly_target
        goal.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(goal)

    logger.info(f"create_new_goal: id={goal.id} title={goal.title!r} type={goal.goal_type}")
    return {
        "id": goal.id,
        "title": goal.title,
        "state": goal.state.value,
        "goal_type": goal.goal_type.value if goal.goal_type else None,
    }


@router.post("/v1/goals/{goal_id}/habit/log", status_code=201)
def log_habit(goal_id: int, db: Session = Depends(get_db)):
    """Record one habit completion for today."""
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    if goal.goal_type != GoalType.habit:
        raise HTTPException(status_code=400, detail="Goal is not a habit goal")

    reading = MetricReading(
        timestamp=datetime.now(timezone.utc),
        metric_type=MetricType.habit_log,
        text_value=str(goal_id),
        value=1.0,
        source=MetricSource.manual,
    )
    db.add(reading)
    db.commit()

    return {"goal_id": goal_id, "this_week_count": _habit_count_this_week(db, goal_id)}


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
