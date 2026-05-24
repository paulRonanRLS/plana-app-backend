"""Unit tests for app/services/drift.py.

Uses SQLite in-memory via test_db fixture. No external services needed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.services import drift as svc
from app.services.drift import DriftEvent, _count_consecutive_outside, _is_outside_range


# ── helpers ────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def make_perpetual_goal(db, title="Weight goal", **kwargs):
    defaults = dict(
        state=GoalState.active,
        goal_type=GoalType.perpetual,
        target_metric_type=MetricType.weight.value,
        target_min=70.0,
        target_max=75.0,
        is_recovering=False,
    )
    defaults.update(kwargs)
    now = _now()
    goal = Goal(title=title, created_at=now, updated_at=now, **defaults)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def _add_at(db, metric_type, value, ts, source=MetricSource.garmin):
    """Insert a MetricReading at an explicit timestamp (SQLite-safe)."""
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    r = MetricReading(timestamp=ts, metric_type=metric_type, value=value, source=source)
    db.add(r)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        r = MetricReading(id=max_id + 1, timestamp=ts, metric_type=metric_type, value=value, source=source)
        db.add(r)
        db.commit()
    return r


def add_reading(db, metric_type, value, days_ago=0, hours_offset=0, source=MetricSource.garmin):
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    ts = _now() - timedelta(days=days_ago, hours=hours_offset)
    r = MetricReading(timestamp=ts, metric_type=metric_type, value=value, source=source)
    db.add(r)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        r = MetricReading(id=max_id + 1, timestamp=ts, metric_type=metric_type, value=value, source=source)
        db.add(r)
        db.commit()
    return r


# ── _is_outside_range unit tests ───────────────────────────────────────────────

def test_outside_range_above_max():
    assert _is_outside_range(80.0, 70.0, 75.0) is True


def test_outside_range_below_min():
    assert _is_outside_range(65.0, 70.0, 75.0) is True


def test_inside_range():
    assert _is_outside_range(72.5, 70.0, 75.0) is False


def test_at_min_boundary():
    assert _is_outside_range(70.0, 70.0, 75.0) is False


def test_at_max_boundary():
    assert _is_outside_range(75.0, 70.0, 75.0) is False


def test_only_min_set_below():
    assert _is_outside_range(65.0, 70.0, None) is True


def test_only_min_set_above():
    assert _is_outside_range(80.0, 70.0, None) is False


def test_only_max_set_above():
    assert _is_outside_range(80.0, None, 75.0) is True


def test_only_max_set_below():
    assert _is_outside_range(65.0, None, 75.0) is False


def test_no_bounds_never_outside():
    assert _is_outside_range(999.0, None, None) is False


# ── _count_consecutive_outside unit tests ──────────────────────────────────────

from datetime import date

def test_count_three_consecutive():
    today = date(2026, 5, 24)
    readings = {
        date(2026, 5, 24): 80.0,
        date(2026, 5, 23): 79.0,
        date(2026, 5, 22): 78.0,
    }
    count, val = _count_consecutive_outside(readings, 70.0, 75.0, today)
    assert count == 3
    assert val == pytest.approx(80.0)


def test_count_breaks_on_in_range():
    today = date(2026, 5, 24)
    readings = {
        date(2026, 5, 24): 80.0,
        date(2026, 5, 23): 72.0,  # in range
        date(2026, 5, 22): 78.0,
    }
    count, val = _count_consecutive_outside(readings, 70.0, 75.0, today)
    assert count == 1


def test_count_breaks_on_gap():
    today = date(2026, 5, 24)
    readings = {
        date(2026, 5, 24): 80.0,
        # gap on 5/23
        date(2026, 5, 22): 78.0,
        date(2026, 5, 21): 77.0,
    }
    count, _ = _count_consecutive_outside(readings, 70.0, 75.0, today)
    assert count == 1


def test_count_returns_most_recent_value():
    today = date(2026, 5, 24)
    readings = {
        date(2026, 5, 24): 82.5,
        date(2026, 5, 23): 81.0,
        date(2026, 5, 22): 80.0,
    }
    _, val = _count_consecutive_outside(readings, 70.0, 75.0, today)
    assert val == pytest.approx(82.5)


def test_count_empty_readings():
    count, val = _count_consecutive_outside({}, 70.0, 75.0, date(2026, 5, 24))
    assert count == 0
    assert val is None


# ── detect_drift integration tests ─────────────────────────────────────────────

def test_no_goals_returns_empty(test_db):
    assert svc.detect_drift(test_db) == []


def test_non_perpetual_goal_not_checked(test_db):
    now = _now()
    goal = Goal(
        title="Run marathon",
        state=GoalState.active,
        goal_type=GoalType.achievement,
        is_recovering=False,
        created_at=now,
        updated_at=now,
    )
    test_db.add(goal)
    test_db.commit()
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_goal_without_type_not_checked(test_db):
    now = _now()
    goal = Goal(
        title="Vague goal",
        state=GoalState.active,
        goal_type=None,
        is_recovering=False,
        created_at=now,
        updated_at=now,
    )
    test_db.add(goal)
    test_db.commit()
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_drifting_goal_not_rechecked(test_db):
    goal = make_perpetual_goal(test_db, state=GoalState.drifting)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_recovering_goal_skipped(test_db):
    goal = make_perpetual_goal(test_db, is_recovering=True)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_draft_goal_skipped(test_db):
    goal = make_perpetual_goal(test_db, state=GoalState.draft)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_released_goal_skipped(test_db):
    goal = make_perpetual_goal(test_db, state=GoalState.released)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_completed_goal_skipped(test_db):
    goal = make_perpetual_goal(test_db, state=GoalState.completed)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_no_metric_type_configured_skipped(test_db):
    goal = make_perpetual_goal(test_db, target_metric_type=None)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    assert svc.detect_drift(test_db) == []


def test_two_days_outside_no_event(test_db):
    make_perpetual_goal(test_db)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=0)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=1)
    assert svc.detect_drift(test_db) == []


def test_three_days_outside_triggers_event(test_db):
    goal = make_perpetual_goal(test_db)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=0)
    add_reading(test_db, MetricType.weight, 79.0, days_ago=1)
    add_reading(test_db, MetricType.weight, 78.0, days_ago=2)
    events = svc.detect_drift(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id
    assert events[0].days_outside_range == 3


def test_five_days_outside_triggers_event(test_db):
    goal = make_perpetual_goal(test_db)
    for i in range(5):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    events = svc.detect_drift(test_db)
    assert len(events) == 1
    assert events[0].days_outside_range == 5


def test_in_range_reading_breaks_streak(test_db):
    make_perpetual_goal(test_db)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=0)
    add_reading(test_db, MetricType.weight, 72.0, days_ago=1)  # in range
    add_reading(test_db, MetricType.weight, 80.0, days_ago=2)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=3)
    assert svc.detect_drift(test_db) == []


def test_gap_in_data_breaks_streak(test_db):
    make_perpetual_goal(test_db)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=0)
    # No reading on day 1 (gap)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=2)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=3)
    assert svc.detect_drift(test_db) == []


def test_event_carries_correct_values(test_db):
    goal = make_perpetual_goal(test_db, target_min=70.0, target_max=75.0)
    add_reading(test_db, MetricType.weight, 79.5, days_ago=0)
    add_reading(test_db, MetricType.weight, 78.0, days_ago=1)
    add_reading(test_db, MetricType.weight, 77.0, days_ago=2)
    events = svc.detect_drift(test_db)
    assert len(events) == 1
    e = events[0]
    assert e.goal_id == goal.id
    assert e.goal_title == "Weight goal"
    assert e.metric_type == MetricType.weight.value
    assert e.days_outside_range == 3
    assert e.current_value == pytest.approx(79.5)
    assert e.target_min == pytest.approx(70.0)
    assert e.target_max == pytest.approx(75.0)


def test_below_min_triggers_drift(test_db):
    make_perpetual_goal(test_db, target_metric_type=MetricType.hrv.value, target_min=55.0, target_max=None)
    for i in range(3):
        add_reading(test_db, MetricType.hrv, 48.0, days_ago=i)
    events = svc.detect_drift(test_db)
    assert len(events) == 1


def test_multiple_readings_same_day_uses_most_recent(test_db):
    """When two readings fall on the same UTC date, only the most recent one counts.

    Uses fixed intra-day timestamps to avoid crossing UTC midnight boundaries.
    """
    make_perpetual_goal(test_db)
    today = _now().date()
    # Anchor to 10:00 and 10:01 UTC on today's date — guaranteed same calendar day
    t_older = datetime(today.year, today.month, today.day, 10, 0, 0, tzinfo=timezone.utc)
    t_newer = datetime(today.year, today.month, today.day, 10, 1, 0, tzinfo=timezone.utc)
    _add_at(test_db, MetricType.weight, 72.0, t_older)   # older, in range
    _add_at(test_db, MetricType.weight, 80.0, t_newer)   # newer, out of range
    add_reading(test_db, MetricType.weight, 80.0, days_ago=1)
    add_reading(test_db, MetricType.weight, 80.0, days_ago=2)
    events = svc.detect_drift(test_db)
    assert len(events) == 1


def test_two_goals_both_drifting(test_db):
    make_perpetual_goal(test_db, title="Weight")
    make_perpetual_goal(test_db, title="HRV", target_metric_type=MetricType.hrv.value, target_min=55.0, target_max=None)
    for i in range(3):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
        add_reading(test_db, MetricType.hrv, 48.0, days_ago=i)
    events = svc.detect_drift(test_db)
    assert len(events) == 2


def test_primacy_goal_drift_detected(test_db):
    """Primacy goals are still checked — drift is surfaced regardless of tier."""
    goal = make_perpetual_goal(test_db, state=GoalState.primacy)
    for i in range(3):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    events = svc.detect_drift(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id


def test_subordinate_goal_drift_detected(test_db):
    goal = make_perpetual_goal(test_db, state=GoalState.subordinate)
    for i in range(3):
        add_reading(test_db, MetricType.weight, 80.0, days_ago=i)
    events = svc.detect_drift(test_db)
    assert len(events) == 1
