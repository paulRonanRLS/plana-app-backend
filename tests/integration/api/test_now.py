"""API integration tests for /v1/now and /v1/health/integrations endpoints."""

import pytest
from datetime import datetime, timedelta, timezone

from app.models.goal import Goal, GoalState, GoalType
from app.models.metric_reading import MetricReading, MetricSource, MetricType


# ── helpers ────────────────────────────────────────────────────────────────────

def _add_perpetual_goal(db, title="Weight", metric_type="weight", target_min=70.0, target_max=75.0):
    now = datetime.now(timezone.utc)
    g = Goal(
        title=title,
        state=GoalState.active,
        goal_type=GoalType.perpetual,
        target_metric_type=metric_type,
        target_min=target_min,
        target_max=target_max,
        created_at=now,
        updated_at=now,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


_reading_id = 0

def _add_reading(db, metric_type_str, value, hours_ago=0):
    global _reading_id
    _reading_id += 1
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    r = MetricReading(
        id=_reading_id,
        timestamp=ts,
        metric_type=MetricType(metric_type_str),
        value=value,
        source=MetricSource.manual,
    )
    db.add(r)
    db.commit()
    return r


# ── GET /v1/now — perpetual goals trend field ──────────────────────────────────

def test_now_perpetual_goal_has_trend_field(test_app, test_db):
    _add_perpetual_goal(test_db)
    data = test_app.get("/v1/now").json()
    for g in data["perpetual_goals"]:
        assert "trend" in g


def test_now_trend_is_none_with_no_readings(test_app, test_db):
    _add_perpetual_goal(test_db)
    data = test_app.get("/v1/now").json()
    pg = data["perpetual_goals"][0]
    assert pg["trend"] is None


def test_now_trend_is_none_with_one_reading(test_app, test_db):
    _add_perpetual_goal(test_db)
    _add_reading(test_db, "weight", 72.0)
    data = test_app.get("/v1/now").json()
    pg = data["perpetual_goals"][0]
    assert pg["trend"] is None


def test_now_trend_up(test_app, test_db):
    _add_perpetual_goal(test_db)
    _add_reading(test_db, "weight", 71.0, hours_ago=24)
    _add_reading(test_db, "weight", 72.5, hours_ago=0)
    data = test_app.get("/v1/now").json()
    pg = data["perpetual_goals"][0]
    assert pg["trend"] == "up"


def test_now_trend_down(test_app, test_db):
    _add_perpetual_goal(test_db)
    _add_reading(test_db, "weight", 73.0, hours_ago=24)
    _add_reading(test_db, "weight", 71.5, hours_ago=0)
    data = test_app.get("/v1/now").json()
    pg = data["perpetual_goals"][0]
    assert pg["trend"] == "down"


def test_now_trend_flat(test_app, test_db):
    _add_perpetual_goal(test_db)
    _add_reading(test_db, "weight", 72.0, hours_ago=24)
    _add_reading(test_db, "weight", 72.0, hours_ago=0)
    data = test_app.get("/v1/now").json()
    pg = data["perpetual_goals"][0]
    assert pg["trend"] == "flat"


# ── GET /v1/health/integrations ───────────────────────────────────────────────

def test_integrations_returns_200(test_app, test_db):
    resp = test_app.get("/v1/health/integrations")
    assert resp.status_code == 200


def test_integrations_has_garmin_and_strava(test_app, test_db):
    data = test_app.get("/v1/health/integrations").json()
    assert "garmin" in data
    assert "strava" in data


def test_integrations_status_never_when_no_redis(test_app, test_db):
    data = test_app.get("/v1/health/integrations").json()
    assert data["garmin"]["status"] == "never"
    assert data["strava"]["status"] == "never"
    assert data["garmin"]["last_sync"] is None
    assert data["strava"]["last_sync"] is None


def test_integrations_shape(test_app, test_db):
    data = test_app.get("/v1/health/integrations").json()
    for key in ("garmin", "strava"):
        assert "last_sync" in data[key]
        assert "status" in data[key]
        assert data[key]["status"] in ("green", "amber", "red", "never")
