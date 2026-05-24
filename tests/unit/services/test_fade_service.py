"""Unit tests for app/services/fade.py.

Uses SQLite in-memory via test_db fixture. No external services needed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.models.milestone import Milestone, MilestoneState
from app.services import fade as svc
from app.services.fade import FADE_DAYS


# ── helpers ────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _ago(days=0, hours=0):
    return _now() - timedelta(days=days, hours=hours)


def make_achievement_goal(db, title="Run a marathon", created_days_ago=20, **kwargs):
    defaults = dict(
        state=GoalState.active,
        goal_type=GoalType.achievement,
        is_recovering=False,
    )
    defaults.update(kwargs)
    created = _ago(days=created_days_ago)
    goal = Goal(title=title, created_at=created, updated_at=created, **defaults)
    db.add(goal)
    db.commit()
    db.refresh(goal)
    return goal


def make_milestone(db, goal_id, updated_days_ago=0):
    now = _now()
    updated = _ago(days=updated_days_ago)
    m = Milestone(
        goal_id=goal_id,
        title="Step",
        state=MilestoneState.active,
        sequence=1,
        created_at=now,
        updated_at=updated,
    )
    db.add(m)
    db.commit()
    return m


def add_telegram_reading(db, days_ago=0):
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError
    ts = _ago(days=days_ago)
    r = MetricReading(timestamp=ts, metric_type=MetricType.subjective_feel, value=1.0, source=MetricSource.telegram)
    db.add(r)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        r = MetricReading(id=max_id + 1, timestamp=ts, metric_type=MetricType.subjective_feel, value=1.0, source=MetricSource.telegram)
        db.add(r)
        db.commit()
    return r


# ── detect_fade tests ──────────────────────────────────────────────────────────

def test_no_goals_returns_empty(test_db):
    assert svc.detect_fade(test_db) == []


def test_draft_goal_skipped(test_db):
    make_achievement_goal(test_db, state=GoalState.draft)
    assert svc.detect_fade(test_db) == []


def test_released_goal_skipped(test_db):
    make_achievement_goal(test_db, state=GoalState.released)
    assert svc.detect_fade(test_db) == []


def test_completed_goal_skipped(test_db):
    make_achievement_goal(test_db, state=GoalState.completed)
    assert svc.detect_fade(test_db) == []


def test_perpetual_goal_not_checked(test_db):
    now = _now()
    created = _ago(days=30)
    goal = Goal(
        title="Weight management",
        state=GoalState.active,
        goal_type=GoalType.perpetual,
        is_recovering=False,
        created_at=created,
        updated_at=created,
    )
    test_db.add(goal)
    test_db.commit()
    assert svc.detect_fade(test_db) == []


def test_goal_created_recently_not_faded(test_db):
    """Goal created less than FADE_DAYS ago should never be flagged as faded."""
    make_achievement_goal(test_db, created_days_ago=FADE_DAYS - 1)
    assert svc.detect_fade(test_db) == []


def test_goal_with_no_activity_fades(test_db):
    """Goal created 20 days ago with no milestones or Telegram captures → fade."""
    goal = make_achievement_goal(test_db, created_days_ago=20)
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id
    assert events[0].days_since_activity == FADE_DAYS
    assert events[0].last_activity_at is None


def test_recent_milestone_prevents_fade(test_db):
    """Milestone updated 3 days ago → not faded."""
    goal = make_achievement_goal(test_db)
    make_milestone(test_db, goal.id, updated_days_ago=3)
    assert svc.detect_fade(test_db) == []


def test_old_milestone_triggers_fade(test_db):
    """Milestone last updated 20 days ago → faded."""
    goal = make_achievement_goal(test_db, created_days_ago=30)
    make_milestone(test_db, goal.id, updated_days_ago=20)
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id
    assert events[0].days_since_activity >= FADE_DAYS


def test_recent_telegram_capture_prevents_fade(test_db):
    """Telegram capture within 14 days → not faded."""
    make_achievement_goal(test_db)
    add_telegram_reading(test_db, days_ago=5)
    assert svc.detect_fade(test_db) == []


def test_old_telegram_capture_triggers_fade(test_db):
    """Telegram capture 20 days ago and no milestone → faded."""
    goal = make_achievement_goal(test_db, created_days_ago=30)
    add_telegram_reading(test_db, days_ago=20)
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id


def test_milestone_beats_telegram_for_recency(test_db):
    """Most recent activity wins — recent milestone overrides old Telegram capture."""
    goal = make_achievement_goal(test_db, created_days_ago=30)
    add_telegram_reading(test_db, days_ago=20)
    make_milestone(test_db, goal.id, updated_days_ago=2)
    assert svc.detect_fade(test_db) == []


def test_fade_event_carries_correct_values(test_db):
    goal = make_achievement_goal(test_db, title="Write the novel", created_days_ago=30)
    make_milestone(test_db, goal.id, updated_days_ago=20)
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    e = events[0]
    assert e.goal_id == goal.id
    assert e.goal_title == "Write the novel"
    assert e.days_since_activity >= FADE_DAYS
    assert e.last_activity_at is not None


def test_fade_event_days_since_activity_accurate(test_db):
    """days_since_activity should reflect actual elapsed time, not just FADE_DAYS."""
    goal = make_achievement_goal(test_db, created_days_ago=40)
    make_milestone(test_db, goal.id, updated_days_ago=25)
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    assert events[0].days_since_activity >= 25


def test_null_goal_type_treated_as_achievement(test_db):
    """Goals with goal_type=None should be checked for fade (default behaviour)."""
    now = _now()
    created = _ago(days=20)
    goal = Goal(
        title="Unnamed goal",
        state=GoalState.active,
        goal_type=None,
        is_recovering=False,
        created_at=created,
        updated_at=created,
    )
    test_db.add(goal)
    test_db.commit()
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id


def test_two_fading_goals_both_reported(test_db):
    g1 = make_achievement_goal(test_db, title="Goal A", created_days_ago=30)
    g2 = make_achievement_goal(test_db, title="Goal B", created_days_ago=30)
    events = svc.detect_fade(test_db)
    assert len(events) == 2
    ids = {e.goal_id for e in events}
    assert g1.id in ids and g2.id in ids


def test_primacy_achievement_goal_fades(test_db):
    """Even a Primacy-tier achievement goal should show fade if inactive."""
    goal = make_achievement_goal(test_db, state=GoalState.primacy, created_days_ago=30)
    events = svc.detect_fade(test_db)
    assert len(events) == 1
    assert events[0].goal_id == goal.id
