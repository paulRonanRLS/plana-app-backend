"""API integration tests for goal management endpoints.

Covers:
  PATCH /v1/goals/{id}          — edit fields
  PATCH /v1/goals/{id}/state    — lifecycle transitions
  GET   /v1/goals/{id}/memoir   — memoir preview
  POST  /v1/goals/{id}/release  — release with user note
  DELETE /v1/goals/{id}         — delete (guarded)
"""

from datetime import datetime, timezone

import pytest

from datetime import date

from app.models.goal import Goal, GoalState, GoalType
from app.models.milestone import Milestone, MilestoneState
from app.models.sacrifice import Sacrifice, ResourceType


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_goal(db, title="Test goal", state=GoalState.active, goal_type=GoalType.achievement):
    now = datetime.now(timezone.utc)
    g = Goal(title=title, state=state, goal_type=goal_type, created_at=now, updated_at=now)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_draft(db, title="Draft goal"):
    return _make_goal(db, title=title, state=GoalState.draft)


def _add_milestone(db, goal_id, state=MilestoneState.pending, title="Milestone"):
    from datetime import date
    now = datetime.now(timezone.utc)
    m = Milestone(
        goal_id=goal_id, title=title, state=state, sequence=1,
        created_at=now, updated_at=now,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _add_sacrifice(db, goal_id):
    now = datetime.now(timezone.utc)
    s = Sacrifice(
        goal_id=goal_id,
        date=date.today(),
        resource=ResourceType.time,
        notes="test",
        created_at=now,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── PATCH /v1/goals/{id} ──────────────────────────────────────────────────────

def test_patch_goal_title(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.patch(f"/v1/goals/{g.id}", json={"title": "Updated title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated title"


def test_patch_goal_description(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.patch(f"/v1/goals/{g.id}", json={"description": "New desc"})
    assert resp.status_code == 200
    test_db.refresh(g)
    assert g.description == "New desc"


def test_patch_goal_perpetual_range(test_app, test_db):
    g = _make_goal(test_db, goal_type=GoalType.perpetual)
    resp = test_app.patch(f"/v1/goals/{g.id}", json={"target_min": 50.0, "target_max": 70.0})
    assert resp.status_code == 200
    test_db.refresh(g)
    assert g.target_min == 50.0
    assert g.target_max == 70.0


def test_patch_goal_weekly_target(test_app, test_db):
    g = _make_goal(test_db, goal_type=GoalType.habit)
    resp = test_app.patch(f"/v1/goals/{g.id}", json={"weekly_target": 4})
    assert resp.status_code == 200
    test_db.refresh(g)
    assert g.weekly_target == 4


def test_patch_goal_target_date(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.patch(f"/v1/goals/{g.id}", json={"target_date": "2027-06-01"})
    assert resp.status_code == 200
    test_db.refresh(g)
    assert str(g.target_date) == "2027-06-01"


def test_patch_goal_not_found(test_app, test_db):
    resp = test_app.patch("/v1/goals/9999", json={"title": "Nope"})
    assert resp.status_code == 404


# ── PATCH /v1/goals/{id}/state ────────────────────────────────────────────────

def test_patch_state_draft_to_active(test_app, test_db):
    g = _make_draft(test_db)
    resp = test_app.patch(f"/v1/goals/{g.id}/state", json={"state": "active"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"


def test_patch_state_active_to_primacy(test_app, test_db):
    g = _make_goal(test_db, state=GoalState.active)
    resp = test_app.patch(f"/v1/goals/{g.id}/state", json={"state": "primacy"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "primacy"


def test_patch_state_active_to_subordinate(test_app, test_db):
    g = _make_goal(test_db, state=GoalState.active)
    resp = test_app.patch(f"/v1/goals/{g.id}/state", json={"state": "subordinate"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "subordinate"


def test_patch_state_primacy_to_active(test_app, test_db):
    g = _make_goal(test_db, state=GoalState.primacy)
    resp = test_app.patch(f"/v1/goals/{g.id}/state", json={"state": "active"})
    assert resp.status_code == 200
    assert resp.json()["state"] == "active"


def test_patch_state_invalid_transition_returns_409(test_app, test_db):
    g = _make_goal(test_db, state=GoalState.active)
    # active → active is not valid
    resp = test_app.patch(f"/v1/goals/{g.id}/state", json={"state": "active"})
    assert resp.status_code == 409


def test_patch_state_unsupported_state_returns_400(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.patch(f"/v1/goals/{g.id}/state", json={"state": "drifting"})
    assert resp.status_code == 400


def test_patch_state_primacy_demotes_existing(test_app, test_db):
    first  = _make_goal(test_db, title="First",  state=GoalState.active)
    second = _make_goal(test_db, title="Second", state=GoalState.active)
    test_app.patch(f"/v1/goals/{first.id}/state",  json={"state": "primacy"})
    test_app.patch(f"/v1/goals/{second.id}/state", json={"state": "primacy"})
    test_db.refresh(first)
    test_db.refresh(second)
    assert first.state  == GoalState.subordinate
    assert second.state == GoalState.primacy


# ── GET /v1/goals/{id}/memoir ─────────────────────────────────────────────────

def test_get_memoir_returns_200(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.get(f"/v1/goals/{g.id}/memoir")
    assert resp.status_code == 200


def test_get_memoir_has_memoir_field(test_app, test_db):
    g = _make_goal(test_db)
    data = test_app.get(f"/v1/goals/{g.id}/memoir").json()
    assert "memoir" in data
    assert isinstance(data["memoir"], str)
    assert len(data["memoir"]) > 0


def test_get_memoir_not_found(test_app, test_db):
    resp = test_app.get("/v1/goals/9999/memoir")
    assert resp.status_code == 404


# ── POST /v1/goals/{id}/release ───────────────────────────────────────────────

def test_release_goal_returns_200(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.post(f"/v1/goals/{g.id}/release", json={"user_note": "Moving on"})
    assert resp.status_code == 200


def test_release_goal_state_is_released(test_app, test_db):
    g = _make_goal(test_db)
    data = test_app.post(f"/v1/goals/{g.id}/release", json={}).json()
    assert data["state"] == "released"


def test_release_goal_stores_user_note(test_app, test_db):
    g = _make_goal(test_db)
    test_app.post(f"/v1/goals/{g.id}/release", json={"user_note": "Not the right time"})
    test_db.refresh(g)
    assert g.release_reason == "Not the right time"


def test_release_goal_stores_memoir(test_app, test_db):
    g = _make_goal(test_db)
    test_app.post(f"/v1/goals/{g.id}/release", json={})
    test_db.refresh(g)
    assert g.memoir is not None


def test_release_goal_from_draft(test_app, test_db):
    g = _make_draft(test_db)
    resp = test_app.post(f"/v1/goals/{g.id}/release", json={})
    assert resp.status_code == 200


def test_release_already_released_returns_409(test_app, test_db):
    g = _make_goal(test_db)
    test_app.post(f"/v1/goals/{g.id}/release", json={})
    resp = test_app.post(f"/v1/goals/{g.id}/release", json={})
    assert resp.status_code == 409


def test_release_not_found(test_app, test_db):
    resp = test_app.post("/v1/goals/9999/release", json={})
    assert resp.status_code == 404


# ── DELETE /v1/goals/{id} ─────────────────────────────────────────────────────

def test_delete_draft_goal_succeeds(test_app, test_db):
    g = _make_draft(test_db)
    resp = test_app.delete(f"/v1/goals/{g.id}")
    assert resp.status_code == 204


def test_delete_active_goal_no_history_succeeds(test_app, test_db):
    g = _make_goal(test_db)
    resp = test_app.delete(f"/v1/goals/{g.id}")
    assert resp.status_code == 204


def test_delete_removes_from_db(test_app, test_db):
    from app.models.goal import Goal as GoalModel
    g = _make_draft(test_db)
    goal_id = g.id
    test_app.delete(f"/v1/goals/{goal_id}")
    assert test_db.query(GoalModel).filter(GoalModel.id == goal_id).first() is None


def test_delete_blocked_by_sacrifice(test_app, test_db):
    g = _make_goal(test_db)
    _add_sacrifice(test_db, g.id)
    resp = test_app.delete(f"/v1/goals/{g.id}")
    assert resp.status_code == 409


def test_delete_blocked_by_achieved_milestone(test_app, test_db):
    g = _make_goal(test_db)
    _add_milestone(test_db, g.id, state=MilestoneState.achieved)
    resp = test_app.delete(f"/v1/goals/{g.id}")
    assert resp.status_code == 409


def test_delete_allowed_with_pending_milestone(test_app, test_db):
    g = _make_goal(test_db)
    _add_milestone(test_db, g.id, state=MilestoneState.pending)
    resp = test_app.delete(f"/v1/goals/{g.id}")
    assert resp.status_code == 204


def test_delete_not_found(test_app, test_db):
    resp = test_app.delete("/v1/goals/9999")
    assert resp.status_code == 404
