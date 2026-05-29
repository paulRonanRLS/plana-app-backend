from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalState, GoalType
from app.models.resource_profile import ResourceProfile


# ── Lifecycle transition table ─────────────────────────────────────────────────

VALID_TRANSITIONS: dict[GoalState, set[GoalState]] = {
    GoalState.draft: {GoalState.active, GoalState.released},
    GoalState.active: {
        GoalState.primacy,
        GoalState.subordinate,
        GoalState.drifting,
        GoalState.released,
        GoalState.completed,
    },
    GoalState.primacy: {
        GoalState.active,
        GoalState.subordinate,
        GoalState.drifting,
        GoalState.released,
        GoalState.completed,
    },
    GoalState.subordinate: {
        GoalState.active,
        GoalState.primacy,
        GoalState.drifting,
        GoalState.released,
        GoalState.completed,
    },
    GoalState.drifting: {
        GoalState.active,
        GoalState.primacy,
        GoalState.subordinate,
        GoalState.released,
        GoalState.completed,
    },
    GoalState.released: set(),
    GoalState.completed: set(),
}

TERMINAL_STATES = frozenset({GoalState.released, GoalState.completed})


def _assert_transition(goal: Goal, new_state: GoalState) -> None:
    if new_state not in VALID_TRANSITIONS[goal.state]:
        allowed = [s.value for s in VALID_TRANSITIONS[goal.state]]
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition '{goal.state}' → '{new_state}'. "
                f"Allowed from '{goal.state}': {allowed or 'none (terminal)'}"
            ),
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ── CRUD ───────────────────────────────────────────────────────────────────────

def create_goal(
    db: Session,
    title: str,
    description: Optional[str] = None,
    target_date: Optional[date] = None,
    weekly_time_hours: Optional[float] = None,
    weekly_tss: Optional[float] = None,
) -> Goal:
    now = _now()
    goal = Goal(
        title=title,
        description=description,
        state=GoalState.draft,
        target_date=target_date,
        weekly_time_hours=weekly_time_hours,
        weekly_tss=weekly_tss,
        created_at=now,
        updated_at=now,
    )
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def get_goal(db: Session, goal_id: int) -> Goal:
    goal = db.query(Goal).filter(Goal.id == goal_id).first()
    if goal is None:
        raise HTTPException(status_code=404, detail=f"Goal {goal_id} not found")
    return goal


def list_goals(
    db: Session,
    state: Optional[GoalState] = None,
) -> list[Goal]:
    q = db.query(Goal)
    if state is not None:
        q = q.filter(Goal.state == state)
    return q.order_by(Goal.created_at.desc()).all()


def update_goal(db: Session, goal_id: int, data: dict) -> Goal:
    """Partial update — only fields present in data are changed."""
    goal = get_goal(db, goal_id)
    for field, value in data.items():
        setattr(goal, field, value)
    goal.updated_at = _now()
    db.commit()
    db.refresh(goal)
    return goal


def delete_goal(db: Session, goal_id: int) -> None:
    goal = get_goal(db, goal_id)
    db.delete(goal)
    db.commit()


# ── Lifecycle ──────────────────────────────────────────────────────────────────

def activate_goal(db: Session, goal_id: int) -> Goal:
    """Draft → Active."""
    goal = get_goal(db, goal_id)
    _assert_transition(goal, GoalState.active)
    goal.state = GoalState.active
    goal.updated_at = _now()
    db.commit()
    db.refresh(goal)
    return goal


def set_primacy(db: Session, goal_id: int) -> Goal:
    """Elevate a goal to Primacy.

    Any existing Primacy goal is automatically demoted to Subordinate — there
    can only be one planA goal at a time.
    """
    goal = get_goal(db, goal_id)
    _assert_transition(goal, GoalState.primacy)

    now = _now()
    for other in db.query(Goal).filter(
        Goal.state == GoalState.primacy, Goal.id != goal_id
    ).all():
        other.state = GoalState.subordinate
        other.updated_at = now

    goal.state = GoalState.primacy
    goal.updated_at = now
    db.commit()
    db.refresh(goal)
    return goal


def set_subordinate(db: Session, goal_id: int) -> Goal:
    """Move a goal to Subordinate (explicitly lower priority)."""
    goal = get_goal(db, goal_id)
    _assert_transition(goal, GoalState.subordinate)
    goal.state = GoalState.subordinate
    goal.updated_at = _now()
    db.commit()
    db.refresh(goal)
    return goal


def mark_drifting(db: Session, goal_id: int) -> Goal:
    """Flag a goal as Drifting (pursuit has lapsed)."""
    goal = get_goal(db, goal_id)
    _assert_transition(goal, GoalState.drifting)
    goal.state = GoalState.drifting
    goal.updated_at = _now()
    db.commit()
    db.refresh(goal)
    return goal


def release_goal(
    db: Session,
    goal_id: int,
    reason: Optional[str] = None,
    memoir: Optional[str] = None,
) -> Goal:
    """Consciously close a goal. Not failure — honest closure."""
    goal = get_goal(db, goal_id)
    _assert_transition(goal, GoalState.released)
    now = _now()
    goal.state = GoalState.released
    goal.released_at = now
    goal.updated_at = now
    if reason is not None:
        goal.release_reason = reason
    if memoir is not None:
        goal.memoir = memoir
    db.commit()
    db.refresh(goal)
    return goal


def complete_goal(
    db: Session,
    goal_id: int,
    memoir: Optional[str] = None,
) -> Goal:
    """Mark a goal achieved."""
    goal = get_goal(db, goal_id)
    _assert_transition(goal, GoalState.completed)
    now = _now()
    goal.state = GoalState.completed
    goal.completed_at = now
    goal.updated_at = now
    if memoir is not None:
        goal.memoir = memoir
    db.commit()
    db.refresh(goal)
    return goal


# ── Resource profile ───────────────────────────────────────────────────────────

def get_current_resource_profile(db: Session) -> Optional[ResourceProfile]:
    """Return this week's resource profile, or None if not yet created."""
    week_start = _iso_week_start(date.today())
    return (
        db.query(ResourceProfile)
        .filter(ResourceProfile.week_start == week_start)
        .first()
    )


def upsert_resource_profile(
    db: Session,
    week_start: Optional[date] = None,
    time_envelope_hours: float = 62.0,
    sleep_hours_per_night: Optional[float] = None,
    work_hours_per_week: Optional[float] = None,
    recovery_envelope_tss: float = 320.0,
    attention_count: Optional[int] = None,
) -> ResourceProfile:
    """Create or update the resource profile for a given week (defaults to current week)."""
    if week_start is None:
        week_start = _iso_week_start(date.today())

    profile = (
        db.query(ResourceProfile)
        .filter(ResourceProfile.week_start == week_start)
        .first()
    )
    now = _now()

    if profile is None:
        profile = ResourceProfile(
            week_start=week_start,
            time_envelope_hours=time_envelope_hours,
            sleep_hours_per_night=sleep_hours_per_night,
            work_hours_per_week=work_hours_per_week,
            recovery_envelope_tss=recovery_envelope_tss,
            attention_count=attention_count,
            created_at=now,
            updated_at=now,
        )
        db.add(profile)
    else:
        profile.time_envelope_hours = time_envelope_hours
        profile.sleep_hours_per_night = sleep_hours_per_night
        profile.work_hours_per_week = work_hours_per_week
        profile.recovery_envelope_tss = recovery_envelope_tss
        profile.attention_count = attention_count
        profile.updated_at = now

    db.commit()
    db.refresh(profile)
    return profile


def get_active_perpetual_goals_by_metric(db: Session, metric_type: str) -> list[Goal]:
    """Return active (non-terminal) perpetual goals tracking the given metric type."""
    return (
        db.query(Goal)
        .filter(
            Goal.goal_type == GoalType.perpetual,
            Goal.target_metric_type == metric_type,
            Goal.state.notin_(list(TERMINAL_STATES)),
        )
        .all()
    )


def get_committed_resources(db: Session) -> dict:
    """Sum of weekly time and TSS committed across all non-terminal goals."""
    active_goals = (
        db.query(Goal)
        .filter(Goal.state.notin_(list(TERMINAL_STATES)))
        .all()
    )
    return {
        "goal_count": len(active_goals),
        "total_time_hours": sum(g.weekly_time_hours or 0.0 for g in active_goals),
        "total_tss": sum(g.weekly_tss or 0.0 for g in active_goals),
    }
