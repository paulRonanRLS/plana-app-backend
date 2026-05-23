"""Resource service — envelope calculation, tension scoring, three-week view.

Four universal resources (from the spec):
  Time       — hours/week after sleep and work (168 - sleep - work)
  Recovery   — TSS budget/week from 90-day Garmin/Strava baseline
  Attention  — count of open milestones + unresolved episodes this week
  Willpower  — longitudinal pattern from sacrifice attribution; never a percentage
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.goal import Goal, GoalState
from app.models.metric_reading import MetricReading, MetricType
from app.models.milestone import Milestone, MilestoneState
from app.models.resource_profile import ResourceProfile
from app.models.sacrifice import Sacrifice, ResourceType
from app.services.goal import TERMINAL_STATES


# ── Internal helpers ───────────────────────────────────────────────────────────

def _iso_week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _week_bounds(week_start: date) -> tuple[datetime, datetime]:
    """Return UTC [start, end) datetime pair for the 7-day week."""
    start = datetime.combine(week_start, time.min).replace(tzinfo=timezone.utc)
    return start, start + timedelta(days=7)


def _active_goals(db: Session) -> list[Goal]:
    return (
        db.query(Goal)
        .filter(Goal.state.notin_(list(TERMINAL_STATES)))
        .all()
    )


def _profile_for_week(db: Session, week_start: date) -> Optional[ResourceProfile]:
    return (
        db.query(ResourceProfile)
        .filter(ResourceProfile.week_start == week_start)
        .first()
    )


# ── Result types ───────────────────────────────────────────────────────────────

@dataclass
class GoalTension:
    goal_id: int
    goal_title: str
    goal_state: str
    time_hours: float       # this goal's weekly time commitment
    tss: float              # this goal's weekly TSS commitment
    time_share: float       # fraction of total committed time (0.0–1.0)
    tss_share: float        # fraction of total committed TSS


@dataclass
class ResourceTension:
    time_envelope_hours: float
    recovery_envelope_tss: float
    total_committed_time_hours: float
    total_committed_tss: float
    time_ratio: float       # committed / envelope — >1.0 means over-committed
    recovery_ratio: float
    attention_count: int
    goals: list[GoalTension] = field(default_factory=list)   # sorted by time_share desc


@dataclass
class WillpowerPattern:
    """Longitudinal sacrifice attribution — not a capacity number."""
    sacrifice_count_28d: int
    dominant_resource: Optional[str]    # resource type with most attributions; None if no data
    by_resource: dict[str, int] = field(default_factory=dict)  # count per ResourceType value


@dataclass
class WeekSnapshot:
    week_start: date
    label: str                          # "last_week" | "this_week" | "next_week"
    time_envelope_hours: float
    time_committed_hours: float
    time_actual_hours: Optional[float]  # None until Garmin/Strava ingestion built (task 7/8)
    recovery_envelope_tss: float
    recovery_committed_tss: float
    recovery_actual_tss: Optional[float]
    attention_count: int
    goal_count: int


@dataclass
class ThreeWeekView:
    last_week: WeekSnapshot
    this_week: WeekSnapshot
    next_week: WeekSnapshot


# ── Pure calculations ──────────────────────────────────────────────────────────

def calculate_time_envelope(
    sleep_hours_per_night: float,
    work_hours_per_week: float,
) -> float:
    """168 hours/week minus sleep and work commitments.

    Spec default: 168 - (8 * 7) - 50 = 62 hrs.
    """
    return 168.0 - (sleep_hours_per_night * 7.0) - work_hours_per_week


# ── DB-backed calculations ─────────────────────────────────────────────────────

def get_tss_baseline(db: Session, days: int = 90) -> float:
    """Average weekly TSS over the past `days` days.

    Reads MetricType.tss entries and averages across the window.
    Returns the spec default (320.0) when no data exists.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    readings = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.tss,
            MetricReading.timestamp >= since,
            MetricReading.value.isnot(None),
        )
        .all()
    )
    if not readings:
        return 320.0
    total_tss = sum(r.value for r in readings)
    return total_tss / (days / 7.0)


def get_attention_count(db: Session, week_start: Optional[date] = None) -> int:
    """Open decisions + active milestones + unresolved episodes for the given week.

    Components:
      - Pending/active milestones belonging to non-terminal goals
      - physical_state and illness_log MetricReadings within the week
    """
    if week_start is None:
        week_start = _iso_week_start(date.today())

    milestone_count = (
        db.query(Milestone)
        .join(Goal, Milestone.goal_id == Goal.id)
        .filter(
            Goal.state.notin_(list(TERMINAL_STATES)),
            Milestone.state.in_([MilestoneState.pending, MilestoneState.active]),
        )
        .count()
    )

    week_start_dt, week_end_dt = _week_bounds(week_start)
    episode_count = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type.in_([MetricType.physical_state, MetricType.illness_log]),
            MetricReading.timestamp >= week_start_dt,
            MetricReading.timestamp < week_end_dt,
        )
        .count()
    )

    return milestone_count + episode_count


def _get_week_tss(db: Session, week_start: date) -> Optional[float]:
    """Sum of TSS MetricReadings within the given week. None if no data."""
    week_start_dt, week_end_dt = _week_bounds(week_start)
    readings = (
        db.query(MetricReading)
        .filter(
            MetricReading.metric_type == MetricType.tss,
            MetricReading.timestamp >= week_start_dt,
            MetricReading.timestamp < week_end_dt,
            MetricReading.value.isnot(None),
        )
        .all()
    )
    return sum(r.value for r in readings) if readings else None


def get_resource_tension(db: Session) -> ResourceTension:
    """Overall resource tension across all non-terminal goals.

    time_ratio and recovery_ratio > 1.0 indicate over-commitment.
    Goals are sorted by time_share descending so the biggest consumers appear first.
    """
    week_start = _iso_week_start(date.today())
    profile = _profile_for_week(db, week_start)
    time_envelope = profile.time_envelope_hours if profile else 62.0
    tss_envelope = profile.recovery_envelope_tss if profile else 320.0

    goals = _active_goals(db)
    total_time = sum(g.weekly_time_hours or 0.0 for g in goals)
    total_tss = sum(g.weekly_tss or 0.0 for g in goals)

    goal_tensions = [
        GoalTension(
            goal_id=g.id,
            goal_title=g.title,
            goal_state=g.state.value,
            time_hours=g.weekly_time_hours or 0.0,
            tss=g.weekly_tss or 0.0,
            time_share=(g.weekly_time_hours or 0.0) / total_time if total_time > 0 else 0.0,
            tss_share=(g.weekly_tss or 0.0) / total_tss if total_tss > 0 else 0.0,
        )
        for g in goals
    ]
    goal_tensions.sort(key=lambda x: x.time_share, reverse=True)

    return ResourceTension(
        time_envelope_hours=time_envelope,
        recovery_envelope_tss=tss_envelope,
        total_committed_time_hours=total_time,
        total_committed_tss=total_tss,
        time_ratio=total_time / time_envelope if time_envelope > 0 else 0.0,
        recovery_ratio=total_tss / tss_envelope if tss_envelope > 0 else 0.0,
        attention_count=get_attention_count(db, week_start),
        goals=goal_tensions,
    )


def get_willpower_pattern(db: Session, days: int = 28) -> WillpowerPattern:
    """Count sacrifice attributions by resource type over the past `days` days.

    Willpower is a pattern signal, not a capacity number — never reduce it to a %.
    """
    since = date.today() - timedelta(days=days)
    sacrifices = (
        db.query(Sacrifice)
        .filter(Sacrifice.date >= since)
        .all()
    )

    by_resource: dict[str, int] = {r.value: 0 for r in ResourceType}
    for s in sacrifices:
        by_resource[s.resource.value] += 1

    dominant = None
    if sacrifices:
        dominant = max(by_resource, key=lambda k: by_resource[k])

    return WillpowerPattern(
        sacrifice_count_28d=len(sacrifices),
        dominant_resource=dominant,
        by_resource=by_resource,
    )


def get_week_snapshot(db: Session, week_start: date, label: str) -> WeekSnapshot:
    """Resource snapshot for a single week."""
    profile = _profile_for_week(db, week_start)
    time_envelope = profile.time_envelope_hours if profile else 62.0
    tss_envelope = profile.recovery_envelope_tss if profile else 320.0

    goals = _active_goals(db)
    committed_time = sum(g.weekly_time_hours or 0.0 for g in goals)
    committed_tss = sum(g.weekly_tss or 0.0 for g in goals)

    return WeekSnapshot(
        week_start=week_start,
        label=label,
        time_envelope_hours=time_envelope,
        time_committed_hours=committed_time,
        time_actual_hours=None,
        recovery_envelope_tss=tss_envelope,
        recovery_committed_tss=committed_tss,
        recovery_actual_tss=_get_week_tss(db, week_start),
        attention_count=get_attention_count(db, week_start),
        goal_count=len(goals),
    )


def get_three_week_view(
    db: Session,
    reference_date: Optional[date] = None,
) -> ThreeWeekView:
    """Three consecutive weekly snapshots centred on the current week.

    last_week  — actuals where available (TSS from MetricReadings)
    this_week  — actuals so far + current commitments
    next_week  — projected from current goal commitments
    """
    today = reference_date or date.today()
    this_week = _iso_week_start(today)
    last_week = this_week - timedelta(weeks=1)
    next_week = this_week + timedelta(weeks=1)

    return ThreeWeekView(
        last_week=get_week_snapshot(db, last_week, "last_week"),
        this_week=get_week_snapshot(db, this_week, "this_week"),
        next_week=get_week_snapshot(db, next_week, "next_week"),
    )
