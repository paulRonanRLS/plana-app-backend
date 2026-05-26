"""Unit tests for app/intelligence/goal_query.py."""

from datetime import date, datetime, timezone

import pytest

from app.intelligence.goal_query import _stub_response, build_context, build_response
from app.models.goal import Goal, GoalState, GoalType
from app.models.milestone import Milestone, MilestoneState
from app.models.sacrifice import Sacrifice, ResourceType


# ── fixtures ───────────────────────────────────────────────────────────────────

def _goal(db, title, state=GoalState.active, goal_type=GoalType.achievement,
          target_date=None, description=None):
    g = Goal(
        title=title,
        state=state,
        goal_type=goal_type,
        description=description,
        target_date=target_date,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _milestone(db, goal_id, title, state=MilestoneState.pending, sequence=1,
               target_date=None, achieved_at=None):
    m = Milestone(
        goal_id=goal_id,
        title=title,
        state=state,
        sequence=sequence,
        target_date=target_date,
        achieved_at=achieved_at,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _sacrifice(db, goal_id, resource=ResourceType.time, days_ago=5):
    from datetime import timedelta
    s = Sacrifice(
        goal_id=goal_id,
        date=date.today() - timedelta(days=days_ago),
        resource=resource,
        created_at=datetime.now(timezone.utc),
    )
    db.add(s)
    db.commit()
    return s


# ── build_context ──────────────────────────────────────────────────────────────

def test_build_context_no_goals_returns_message(test_db):
    assert build_context([], test_db) == "No active goals."


def test_build_context_no_active_goals(test_db):
    from app.models.goal import GoalState
    g = _goal(test_db, "Done", state=GoalState.completed)
    assert build_context([g], test_db) == "No active goals."


def test_build_context_includes_goal_title(test_db):
    g = _goal(test_db, "Half Marathon")
    ctx = build_context([g], test_db)
    assert "Half Marathon" in ctx


def test_build_context_includes_state(test_db):
    g = _goal(test_db, "Half Marathon", state=GoalState.active)
    ctx = build_context([g], test_db)
    assert "[active]" in ctx


def test_build_context_includes_primacy_state(test_db):
    g = _goal(test_db, "Big Race", state=GoalState.primacy)
    ctx = build_context([g], test_db)
    assert "[primacy]" in ctx


def test_build_context_includes_target_date(test_db):
    g = _goal(test_db, "Marathon", target_date=date(2026, 10, 15))
    ctx = build_context([g], test_db)
    assert "2026-10-15" in ctx


def test_build_context_no_milestones_label(test_db):
    g = _goal(test_db, "Goal With No Milestones")
    ctx = build_context([g], test_db)
    assert "Milestones: none" in ctx


def test_build_context_includes_milestone_titles(test_db):
    g = _goal(test_db, "Half Marathon")
    _milestone(test_db, g.id, "Run 10k under 50 min", sequence=1)
    _milestone(test_db, g.id, "Long run 15k", sequence=2)
    ctx = build_context([g], test_db)
    assert "Run 10k under 50 min" in ctx
    assert "Long run 15k" in ctx


def test_build_context_includes_milestone_states(test_db):
    g = _goal(test_db, "Half Marathon")
    _milestone(test_db, g.id, "First milestone", state=MilestoneState.achieved, sequence=1)
    _milestone(test_db, g.id, "Second milestone", state=MilestoneState.pending, sequence=2)
    ctx = build_context([g], test_db)
    assert "[achieved]" in ctx
    assert "[pending]" in ctx


def test_build_context_includes_milestone_count(test_db):
    g = _goal(test_db, "Half Marathon")
    _milestone(test_db, g.id, "M1", sequence=1)
    _milestone(test_db, g.id, "M2", sequence=2)
    ctx = build_context([g], test_db)
    assert "Milestones (2)" in ctx


def test_build_context_zero_sacrifices(test_db):
    g = _goal(test_db, "No Sacrifice Goal")
    ctx = build_context([g], test_db)
    assert "Sacrifices (last 30 days): 0" in ctx


def test_build_context_sacrifice_count(test_db):
    g = _goal(test_db, "Sacrifice Goal")
    _sacrifice(test_db, g.id, ResourceType.time, days_ago=5)
    _sacrifice(test_db, g.id, ResourceType.recovery, days_ago=10)
    ctx = build_context([g], test_db)
    assert "Sacrifices (last 30 days): 2" in ctx


def test_build_context_sacrifice_excludes_old(test_db):
    g = _goal(test_db, "Goal")
    _sacrifice(test_db, g.id, ResourceType.time, days_ago=35)  # outside 30-day window
    ctx = build_context([g], test_db)
    assert "Sacrifices (last 30 days): 0" in ctx


def test_build_context_sacrifice_resource_in_summary(test_db):
    g = _goal(test_db, "Goal")
    _sacrifice(test_db, g.id, ResourceType.willpower, days_ago=3)
    ctx = build_context([g], test_db)
    assert "willpower" in ctx


def test_build_context_excludes_released_goal(test_db):
    g = _goal(test_db, "Old Goal", state=GoalState.released)
    ctx = build_context([g], test_db)
    assert "No active goals." == ctx


def test_build_context_multiple_goals(test_db):
    g1 = _goal(test_db, "Half Marathon")
    g2 = _goal(test_db, "Photography")
    ctx = build_context([g1, g2], test_db)
    assert "Half Marathon" in ctx
    assert "Photography" in ctx


def test_build_context_includes_description(test_db):
    g = _goal(test_db, "Half Marathon", description="Sub-2h half marathon")
    ctx = build_context([g], test_db)
    assert "Sub-2h half marathon" in ctx


# ── _stub_response ─────────────────────────────────────────────────────────────

def test_stub_response_no_goals(test_db):
    result = _stub_response([], test_db)
    assert "No active goals" in result


def test_stub_response_counts_milestones(test_db):
    g = _goal(test_db, "Half Marathon")
    _milestone(test_db, g.id, "M1", state=MilestoneState.achieved, sequence=1)
    _milestone(test_db, g.id, "M2", state=MilestoneState.pending, sequence=2)
    result = _stub_response([g], test_db)
    assert "Half Marathon" in result
    assert "1/2" in result


def test_stub_response_zero_milestones(test_db):
    g = _goal(test_db, "Empty Goal")
    result = _stub_response([g], test_db)
    assert "0/0" in result


# ── build_response (stub path) ─────────────────────────────────────────────────

def test_build_response_no_client_uses_stub(test_db):
    g = _goal(test_db, "Half Marathon")
    _milestone(test_db, g.id, "M1", state=MilestoneState.achieved, sequence=1)
    result = build_response("how am I doing?", [g], test_db, client=None)
    assert "Half Marathon" in result
    assert "1/1" in result
