"""Unit tests for app/services/goal.py.

Uses the SQLite in-memory test_db fixture — no PostgreSQL required.
All lifecycle transitions, CRUD paths, and resource profile methods are covered.
"""

from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models.goal import GoalState, GoalType
from app.models.resource_profile import ResourceProfile
from app.services import goal as svc


# ── helpers ────────────────────────────────────────────────────────────────────

def make_goal(db, title="Run a marathon", **kwargs):
    return svc.create_goal(db, title=title, **kwargs)


def make_active_goal(db, title="Run a marathon", **kwargs):
    g = make_goal(db, title=title, **kwargs)
    return svc.activate_goal(db, g.id)


# ── CRUD ───────────────────────────────────────────────────────────────────────

def test_create_goal_minimal(test_db):
    goal = make_goal(test_db)
    assert goal.id is not None
    assert goal.title == "Run a marathon"
    assert goal.state == GoalState.draft
    assert goal.description is None
    assert goal.target_date is None
    assert goal.weekly_time_hours is None
    assert goal.weekly_tss is None
    assert goal.created_at is not None
    assert goal.updated_at is not None


def test_create_goal_full(test_db):
    td = date(2026, 12, 31)
    goal = make_goal(
        test_db,
        title="Finish the novel",
        description="Write 80k words",
        target_date=td,
        weekly_time_hours=10.0,
        weekly_tss=50.0,
    )
    assert goal.description == "Write 80k words"
    assert goal.target_date == td
    assert goal.weekly_time_hours == 10.0
    assert goal.weekly_tss == 50.0


def test_get_goal_found(test_db):
    created = make_goal(test_db)
    fetched = svc.get_goal(test_db, created.id)
    assert fetched.id == created.id
    assert fetched.title == created.title


def test_get_goal_not_found(test_db):
    with pytest.raises(HTTPException) as exc:
        svc.get_goal(test_db, 9999)
    assert exc.value.status_code == 404


def test_list_goals_empty(test_db):
    assert svc.list_goals(test_db) == []


def test_list_goals_all(test_db):
    make_goal(test_db, title="Goal A")
    make_goal(test_db, title="Goal B")
    goals = svc.list_goals(test_db)
    assert len(goals) == 2


def test_list_goals_filtered_by_state(test_db):
    g1 = make_goal(test_db, title="Draft goal")
    g2 = make_active_goal(test_db, title="Active goal")

    drafts = svc.list_goals(test_db, state=GoalState.draft)
    actives = svc.list_goals(test_db, state=GoalState.active)

    assert len(drafts) == 1 and drafts[0].id == g1.id
    assert len(actives) == 1 and actives[0].id == g2.id


def test_update_goal_partial(test_db):
    goal = make_goal(test_db, title="Original title")
    original_updated_at = goal.updated_at

    updated = svc.update_goal(test_db, goal.id, {"title": "New title", "description": "Added desc"})

    assert updated.title == "New title"
    assert updated.description == "Added desc"
    assert updated.state == GoalState.draft          # unchanged
    assert updated.updated_at >= original_updated_at


def test_update_goal_not_found(test_db):
    with pytest.raises(HTTPException) as exc:
        svc.update_goal(test_db, 9999, {"title": "Nope"})
    assert exc.value.status_code == 404


def test_delete_goal(test_db):
    goal = make_goal(test_db)
    goal_id = goal.id
    svc.delete_goal(test_db, goal_id)
    with pytest.raises(HTTPException) as exc:
        svc.get_goal(test_db, goal_id)
    assert exc.value.status_code == 404


def test_delete_goal_not_found(test_db):
    with pytest.raises(HTTPException) as exc:
        svc.delete_goal(test_db, 9999)
    assert exc.value.status_code == 404


# ── Lifecycle — forward transitions ────────────────────────────────────────────

def test_activate_goal(test_db):
    goal = make_goal(test_db)
    assert goal.state == GoalState.draft
    activated = svc.activate_goal(test_db, goal.id)
    assert activated.state == GoalState.active


def test_activate_goal_invalid_from_active(test_db):
    goal = make_active_goal(test_db)
    with pytest.raises(HTTPException) as exc:
        svc.activate_goal(test_db, goal.id)   # active → active not allowed
    assert exc.value.status_code == 409


def test_set_primacy_from_active(test_db):
    goal = make_active_goal(test_db)
    primacy = svc.set_primacy(test_db, goal.id)
    assert primacy.state == GoalState.primacy


def test_set_primacy_demotes_existing_primacy(test_db):
    first = make_active_goal(test_db, title="First primacy")
    second = make_active_goal(test_db, title="Second primacy")

    svc.set_primacy(test_db, first.id)
    svc.set_primacy(test_db, second.id)

    # first should now be subordinate
    reloaded_first = svc.get_goal(test_db, first.id)
    reloaded_second = svc.get_goal(test_db, second.id)

    assert reloaded_first.state == GoalState.subordinate
    assert reloaded_second.state == GoalState.primacy


def test_set_primacy_invalid_from_draft(test_db):
    goal = make_goal(test_db)
    with pytest.raises(HTTPException) as exc:
        svc.set_primacy(test_db, goal.id)
    assert exc.value.status_code == 409


def test_set_subordinate(test_db):
    goal = make_active_goal(test_db)
    sub = svc.set_subordinate(test_db, goal.id)
    assert sub.state == GoalState.subordinate


def test_mark_drifting(test_db):
    goal = make_active_goal(test_db)
    drifting = svc.mark_drifting(test_db, goal.id)
    assert drifting.state == GoalState.drifting


def test_release_goal_with_reason(test_db):
    goal = make_active_goal(test_db)
    released = svc.release_goal(test_db, goal.id, reason="Life changed direction")
    assert released.state == GoalState.released
    assert released.release_reason == "Life changed direction"
    assert released.released_at is not None


def test_release_goal_with_memoir(test_db):
    goal = make_active_goal(test_db)
    released = svc.release_goal(test_db, goal.id, memoir="It was worth the attempt.")
    assert released.memoir == "It was worth the attempt."


def test_release_from_draft(test_db):
    goal = make_goal(test_db)
    released = svc.release_goal(test_db, goal.id, reason="Never started")
    assert released.state == GoalState.released


def test_complete_goal(test_db):
    goal = make_active_goal(test_db)
    completed = svc.complete_goal(test_db, goal.id, memoir="Did it.")
    assert completed.state == GoalState.completed
    assert completed.completed_at is not None
    assert completed.memoir == "Did it."


# ── Lifecycle — terminal state enforcement ─────────────────────────────────────

def test_released_blocks_all_transitions(test_db):
    goal = make_active_goal(test_db)
    svc.release_goal(test_db, goal.id)

    for fn in (
        lambda: svc.activate_goal(test_db, goal.id),
        lambda: svc.set_primacy(test_db, goal.id),
        lambda: svc.set_subordinate(test_db, goal.id),
        lambda: svc.mark_drifting(test_db, goal.id),
        lambda: svc.complete_goal(test_db, goal.id),
        lambda: svc.release_goal(test_db, goal.id),
    ):
        with pytest.raises(HTTPException) as exc:
            fn()
        assert exc.value.status_code == 409


def test_completed_blocks_all_transitions(test_db):
    goal = make_active_goal(test_db)
    svc.complete_goal(test_db, goal.id)

    for fn in (
        lambda: svc.activate_goal(test_db, goal.id),
        lambda: svc.release_goal(test_db, goal.id),
        lambda: svc.complete_goal(test_db, goal.id),
    ):
        with pytest.raises(HTTPException) as exc:
            fn()
        assert exc.value.status_code == 409


# ── Lifecycle — re-engagement from drifting/subordinate ────────────────────────

def test_drifting_can_reactivate(test_db):
    goal = make_active_goal(test_db)
    svc.mark_drifting(test_db, goal.id)
    reactivated = svc.activate_goal(test_db, goal.id)
    assert reactivated.state == GoalState.active


def test_subordinate_can_reactivate(test_db):
    goal = make_active_goal(test_db)
    svc.set_subordinate(test_db, goal.id)
    reactivated = svc.activate_goal(test_db, goal.id)
    assert reactivated.state == GoalState.active


def test_drifting_can_become_primacy(test_db):
    goal = make_active_goal(test_db)
    svc.mark_drifting(test_db, goal.id)
    elevated = svc.set_primacy(test_db, goal.id)
    assert elevated.state == GoalState.primacy


# ── Resource profile ───────────────────────────────────────────────────────────

def test_get_current_resource_profile_none(test_db):
    profile = svc.get_current_resource_profile(test_db)
    assert profile is None


def test_upsert_resource_profile_creates(test_db):
    profile = svc.upsert_resource_profile(
        test_db,
        time_envelope_hours=55.0,
        sleep_hours_per_night=7.5,
        work_hours_per_week=45.0,
        recovery_envelope_tss=300.0,
    )
    assert profile.id is not None
    assert profile.time_envelope_hours == 55.0
    assert profile.sleep_hours_per_night == 7.5
    assert profile.work_hours_per_week == 45.0
    assert profile.recovery_envelope_tss == 300.0


def test_upsert_resource_profile_updates_existing(test_db):
    week = date(2026, 5, 18)  # a Monday
    svc.upsert_resource_profile(test_db, week_start=week, time_envelope_hours=60.0)
    updated = svc.upsert_resource_profile(test_db, week_start=week, time_envelope_hours=50.0)

    assert updated.time_envelope_hours == 50.0

    # Only one row for that week
    count = test_db.query(ResourceProfile).filter(ResourceProfile.week_start == week).count()
    assert count == 1


def test_upsert_resource_profile_defaults(test_db):
    profile = svc.upsert_resource_profile(test_db)
    assert profile.time_envelope_hours == 62.0
    assert profile.recovery_envelope_tss == 320.0


def test_get_current_resource_profile_after_upsert(test_db):
    svc.upsert_resource_profile(test_db)
    profile = svc.get_current_resource_profile(test_db)
    assert profile is not None
    assert profile.time_envelope_hours == 62.0


def test_get_committed_resources_empty(test_db):
    result = svc.get_committed_resources(test_db)
    assert result == {"goal_count": 0, "total_time_hours": 0.0, "total_tss": 0.0}


def test_get_committed_resources_sums_active_goals(test_db):
    make_active_goal(test_db, title="Goal A", weekly_time_hours=8.0, weekly_tss=100.0)
    make_active_goal(test_db, title="Goal B", weekly_time_hours=5.0, weekly_tss=80.0)

    result = svc.get_committed_resources(test_db)
    assert result["goal_count"] == 2
    assert result["total_time_hours"] == 13.0
    assert result["total_tss"] == 180.0


def test_get_committed_resources_excludes_terminal(test_db):
    active = make_active_goal(test_db, title="Active", weekly_time_hours=8.0, weekly_tss=100.0)
    finished = make_active_goal(test_db, title="Done", weekly_time_hours=5.0, weekly_tss=80.0)
    svc.complete_goal(test_db, finished.id)

    result = svc.get_committed_resources(test_db)
    assert result["goal_count"] == 1
    assert result["total_time_hours"] == 8.0
    assert result["total_tss"] == 100.0


def test_get_committed_resources_handles_null_allocations(test_db):
    # Goals without time/TSS set should count as 0, not error
    make_active_goal(test_db, title="No allocation")

    result = svc.get_committed_resources(test_db)
    assert result["goal_count"] == 1
    assert result["total_time_hours"] == 0.0
    assert result["total_tss"] == 0.0


# ── get_active_perpetual_goals_by_metric ──────────────────────────────────────

def _make_perpetual(db, metric_type: str, title=None):
    g = make_active_goal(db, title=title or f"Perpetual {metric_type}")
    g.goal_type = GoalType.perpetual
    g.target_metric_type = metric_type
    db.commit()
    db.refresh(g)
    return g


def test_duplicate_metric_found(test_db):
    _make_perpetual(test_db, "hrv")
    result = svc.get_active_perpetual_goals_by_metric(test_db, "hrv")
    assert len(result) == 1
    assert result[0].target_metric_type == "hrv"


def test_duplicate_metric_not_found_for_different_metric(test_db):
    _make_perpetual(test_db, "hrv")
    result = svc.get_active_perpetual_goals_by_metric(test_db, "sleep_score")
    assert result == []


def test_duplicate_metric_excludes_released(test_db):
    g = _make_perpetual(test_db, "hrv")
    svc.release_goal(test_db, g.id)
    result = svc.get_active_perpetual_goals_by_metric(test_db, "hrv")
    assert result == []


def test_duplicate_metric_excludes_completed(test_db):
    g = _make_perpetual(test_db, "hrv")
    svc.complete_goal(test_db, g.id)
    result = svc.get_active_perpetual_goals_by_metric(test_db, "hrv")
    assert result == []


def test_duplicate_metric_ignores_non_perpetual(test_db):
    g = make_active_goal(test_db, title="Not perpetual")
    g.target_metric_type = "hrv"
    test_db.commit()
    result = svc.get_active_perpetual_goals_by_metric(test_db, "hrv")
    assert result == []
