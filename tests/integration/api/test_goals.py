"""API integration tests for POST /v1/goals duplicate perpetual detection."""

from app.models.goal import GoalType
from app.services.goal import activate_goal, create_goal


def _make_perpetual(db, metric_type: str):
    g = create_goal(db, title=f"Perpetual {metric_type}")
    g = activate_goal(db, g.id)
    g.goal_type = GoalType.perpetual
    g.target_metric_type = metric_type
    db.commit()
    db.refresh(g)
    return g


# ── duplicate perpetual metric ────────────────────────────────────────────────

def test_duplicate_perpetual_returns_400(test_app, test_db):
    _make_perpetual(test_db, "hrv")
    resp = test_app.post("/v1/goals", json={
        "title": "HRV goal 2",
        "goal_type": "perpetual",
        "target_metric_type": "hrv",
    })
    assert resp.status_code == 400
    assert resp.json()["detail"] == "An active goal for this metric already exists."


def test_duplicate_perpetual_different_metric_returns_201(test_app, test_db):
    _make_perpetual(test_db, "hrv")
    resp = test_app.post("/v1/goals", json={
        "title": "Sleep goal",
        "goal_type": "perpetual",
        "target_metric_type": "sleep_score",
    })
    assert resp.status_code == 201


def test_perpetual_no_metric_type_not_blocked(test_app, test_db):
    _make_perpetual(test_db, "hrv")
    resp = test_app.post("/v1/goals", json={
        "title": "Generic perpetual",
        "goal_type": "perpetual",
    })
    assert resp.status_code == 201


def test_released_perpetual_allows_new_goal(test_app, test_db):
    from app.services.goal import release_goal
    g = _make_perpetual(test_db, "hrv")
    release_goal(test_db, g.id)
    resp = test_app.post("/v1/goals", json={
        "title": "HRV goal again",
        "goal_type": "perpetual",
        "target_metric_type": "hrv",
    })
    assert resp.status_code == 201


def test_non_perpetual_not_blocked_by_metric(test_app, test_db):
    _make_perpetual(test_db, "hrv")
    resp = test_app.post("/v1/goals", json={
        "title": "Achieve something",
        "goal_type": "achievement",
        "target_metric_type": "hrv",
    })
    assert resp.status_code == 201
