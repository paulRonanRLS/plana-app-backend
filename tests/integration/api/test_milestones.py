"""API integration tests for milestone endpoints.

Uses the in-memory SQLite test_app fixture with all external services stubbed.
All tests run without a real DB, Claude, or Telegram connection.
"""

import pytest

from app.models.goal import GoalState
from app.services.goal import create_goal, activate_goal


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_active_goal(db, title="Run a marathon"):
    g = create_goal(db, title=title, description="Sub-4 hour finish")
    return activate_goal(db, g.id)


# ── POST /v1/goals/{id}/milestones/suggest ─────────────────────────────────────

def test_suggest_returns_200(test_app, test_db):
    goal = _make_active_goal(test_db)
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    assert resp.status_code == 200


def test_suggest_returns_three_stub_milestones(test_app, test_db):
    goal = _make_active_goal(test_db)
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    data = resp.json()
    assert len(data["suggestions"]) == 3


def test_suggest_infers_run_from_goal_title(test_app, test_db):
    goal = _make_active_goal(test_db, title="Run a marathon")
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    data = resp.json()
    assert data["activity_type"] == "run"


def test_suggest_accepts_explicit_activity_type(test_app, test_db):
    goal = _make_active_goal(test_db, title="Get fitter")
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={"activity_type": "ride"})
    data = resp.json()
    assert data["activity_type"] == "ride"


def test_suggest_milestones_have_required_fields(test_app, test_db):
    goal = _make_active_goal(test_db)
    data = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={}).json()
    for m in data["suggestions"]:
        assert "title" in m
        assert "sequence" in m


def test_suggest_404_for_unknown_goal(test_app, test_db):
    resp = test_app.post("/v1/goals/99999/milestones/suggest", json={})
    assert resp.status_code == 404


def test_suggest_includes_capability_snapshot(test_app, test_db):
    goal = _make_active_goal(test_db)
    data = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={}).json()
    assert "capability" in data
    assert "goal_type" in data["capability"]


def test_suggest_goal_id_in_response(test_app, test_db):
    goal = _make_active_goal(test_db)
    data = test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={}).json()
    assert data["goal_id"] == goal.id


# ── POST /v1/goals/{id}/milestones/agree ──────────────────────────────────────

def test_agree_saves_milestones(test_app, test_db):
    goal = _make_active_goal(test_db)
    payload = {
        "milestones": [
            {"title": "First 10k", "description": "Run 10km comfortably", "target_date": "2026-06-01"},
            {"title": "Half marathon", "description": "Complete 21km", "target_date": "2026-08-01"},
        ]
    }
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["milestones"]) == 2


def test_agree_returns_correct_goal_id(test_app, test_db):
    goal = _make_active_goal(test_db)
    payload = {"milestones": [{"title": "Step 1"}]}
    data = test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json=payload).json()
    assert data["goal_id"] == goal.id


def test_agree_milestones_have_pending_state(test_app, test_db):
    goal = _make_active_goal(test_db)
    payload = {"milestones": [{"title": "Build base"}]}
    data = test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json=payload).json()
    assert data["milestones"][0]["state"] == "pending"


def test_agree_empty_list_returns_422(test_app, test_db):
    goal = _make_active_goal(test_db)
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json={"milestones": []})
    assert resp.status_code == 422


def test_agree_404_for_unknown_goal(test_app, test_db):
    payload = {"milestones": [{"title": "Step"}]}
    resp = test_app.post("/v1/goals/99999/milestones/agree", json=payload)
    assert resp.status_code == 404


# ── GET /v1/goals/{id}/milestones ─────────────────────────────────────────────

def test_list_milestones_empty(test_app, test_db):
    goal = _make_active_goal(test_db)
    data = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    assert data["milestones"] == []


def test_list_milestones_after_agree(test_app, test_db):
    goal = _make_active_goal(test_db)
    payload = {"milestones": [{"title": "A"}, {"title": "B"}, {"title": "C"}]}
    test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json=payload)
    data = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    assert len(data["milestones"]) == 3


def test_list_milestones_404_for_unknown_goal(test_app, test_db):
    resp = test_app.get("/v1/goals/99999/milestones")
    assert resp.status_code == 404


def test_list_milestones_ordered_by_sequence(test_app, test_db):
    goal = _make_active_goal(test_db)
    payload = {
        "milestones": [
            {"title": "First", "sequence": 1},
            {"title": "Third", "sequence": 3},
            {"title": "Second", "sequence": 2},
        ]
    }
    test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json=payload)
    data = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    titles = [m["title"] for m in data["milestones"]]
    assert titles == ["First", "Second", "Third"]


# ── PATCH /v1/goals/{id}/milestones/{milestone_id} ────────────────────────────

def _agree_one(test_app, test_db, goal_id, title="Step 1"):
    payload = {"milestones": [{"title": title}]}
    data = test_app.post(f"/v1/goals/{goal_id}/milestones/agree", json=payload).json()
    return data["milestones"][0]["id"]


def test_patch_updates_title(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    resp = test_app.patch(f"/v1/goals/{goal.id}/milestones/{mid}", json={"title": "Updated title"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated title"


def test_patch_marks_achieved(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    resp = test_app.patch(f"/v1/goals/{goal.id}/milestones/{mid}", json={"state": "achieved"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "achieved"
    assert data["achieved_at"] is not None


def test_patch_adjusts_target_date(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    resp = test_app.patch(f"/v1/goals/{goal.id}/milestones/{mid}", json={"target_date": "2026-09-01"})
    assert resp.status_code == 200
    assert resp.json()["target_date"] == "2026-09-01"


def test_patch_404_for_wrong_goal(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    resp = test_app.patch(f"/v1/goals/99999/milestones/{mid}", json={"title": "X"})
    assert resp.status_code == 404


def test_patch_404_for_unknown_milestone(test_app, test_db):
    goal = _make_active_goal(test_db)
    resp = test_app.patch(f"/v1/goals/{goal.id}/milestones/99999", json={"title": "X"})
    assert resp.status_code == 404


def test_patch_saves_tracking_fields(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id, title="Get zone 2 training to 5min kms")
    resp = test_app.patch(
        f"/v1/goals/{goal.id}/milestones/{mid}",
        json={
            "activity_type": "run",
            "progress_type": "single_effort",
            "metric": "pace_per_km",
            "target_value": 5.0,
            "period": "lifetime",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["activity_type"] == "run"
    assert data["progress_type"] == "single_effort"
    assert data["metric"] == "pace_per_km"
    assert data["target_value"] == 5.0
    assert data["period"] == "lifetime"


def test_patch_tracking_fields_persisted_in_db(test_app, test_db):
    from app.models.milestone import Milestone
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    test_app.patch(
        f"/v1/goals/{goal.id}/milestones/{mid}",
        json={"activity_type": "run", "progress_type": "single_effort",
              "metric": "pace_per_km", "target_value": 5.0, "period": "lifetime"},
    )
    test_db.expire_all()
    m = test_db.query(Milestone).filter(Milestone.id == mid).first()
    assert m.activity_type == "run"
    assert m.progress_type.value == "single_effort"
    assert m.metric.value == "pace_per_km"
    assert m.target_value == 5.0
    assert m.period.value == "lifetime"


def test_patch_tracking_fields_can_be_cleared(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    test_app.patch(
        f"/v1/goals/{goal.id}/milestones/{mid}",
        json={"activity_type": "run", "metric": "distance_km", "target_value": 10.0},
    )
    resp = test_app.patch(
        f"/v1/goals/{goal.id}/milestones/{mid}",
        json={"activity_type": None, "metric": None, "target_value": None},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["activity_type"] is None
    assert data["metric"] is None
    assert data["target_value"] is None


# ── DELETE /v1/goals/{id}/milestones/{milestone_id} ───────────────────────────

def test_delete_milestone_returns_204(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    resp = test_app.delete(f"/v1/goals/{goal.id}/milestones/{mid}")
    assert resp.status_code == 204


def test_delete_milestone_removes_from_list(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    test_app.delete(f"/v1/goals/{goal.id}/milestones/{mid}")
    data = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    assert all(m["id"] != mid for m in data["milestones"])


def test_delete_milestone_404_unknown(test_app, test_db):
    goal = _make_active_goal(test_db)
    resp = test_app.delete(f"/v1/goals/{goal.id}/milestones/99999")
    assert resp.status_code == 404


def test_delete_milestone_404_wrong_goal(test_app, test_db):
    goal = _make_active_goal(test_db)
    mid = _agree_one(test_app, test_db, goal.id)
    resp = test_app.delete(f"/v1/goals/99999/milestones/{mid}")
    assert resp.status_code == 404


# ── suggested → pending transition ────────────────────────────────────────────

def test_suggest_saves_milestones_as_suggested(test_app, test_db):
    goal = _make_active_goal(test_db)
    test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    data = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    assert all(m["state"] == "suggested" for m in data["milestones"])


def test_agree_transitions_suggested_to_pending(test_app, test_db):
    goal = _make_active_goal(test_db)
    test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    data = test_app.post(
        f"/v1/goals/{goal.id}/milestones/agree", json={"milestones": []}
    ).json()
    assert all(m["state"] == "pending" for m in data["milestones"])


def test_agree_transitions_all_suggested_on_goal(test_app, test_db):
    goal = _make_active_goal(test_db)
    test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    before = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    suggested_count = sum(1 for m in before["milestones"] if m["state"] == "suggested")
    assert suggested_count == 3

    test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json={"milestones": []})
    after = test_app.get(f"/v1/goals/{goal.id}/milestones").json()
    assert all(m["state"] == "pending" for m in after["milestones"])
    assert len(after["milestones"]) == 3


def test_agree_empty_body_with_no_suggested_returns_422(test_app, test_db):
    goal = _make_active_goal(test_db)
    resp = test_app.post(f"/v1/goals/{goal.id}/milestones/agree", json={"milestones": []})
    assert resp.status_code == 422


def test_agree_body_milestones_plus_existing_suggested(test_app, test_db):
    goal = _make_active_goal(test_db)
    test_app.post(f"/v1/goals/{goal.id}/milestones/suggest", json={})
    resp = test_app.post(
        f"/v1/goals/{goal.id}/milestones/agree",
        json={"milestones": [{"title": "Extra step"}]},
    )
    assert resp.status_code == 200
    data = resp.json()
    # 3 transitioned from suggested + 1 created = 4 total
    assert len(data["milestones"]) == 4
    assert all(m["state"] == "pending" for m in data["milestones"])
