"""API integration tests for /v1/now and /v1/health/integrations endpoints."""

import json
import pytest
from datetime import date, datetime, timedelta, timezone

from app.models.goal import Goal, GoalState, GoalType, HabitPeriod, HabitType
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

def _add_reading(db, metric_type_str, value, hours_ago=0, source=MetricSource.manual):
    global _reading_id
    _reading_id += 1
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    r = MetricReading(
        id=_reading_id,
        timestamp=ts,
        metric_type=MetricType(metric_type_str),
        value=value,
        source=source,
    )
    db.add(r)
    db.commit()
    return r


def _add_strava_activity(db, hours_ago=0, activity_type="Run", distance_km=10.0, tss=80):
    global _reading_id
    _reading_id += 1
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    r = MetricReading(
        id=_reading_id,
        timestamp=ts,
        metric_type=MetricType.activity,
        source=MetricSource.strava,
        notes=json.dumps({
            "strava_id": _reading_id,
            "type": activity_type,
            "distance_km": distance_km,
            "tss": tss,
        }),
    )
    db.add(r)
    db.commit()
    return r


def _make_goal(db, title, goal_type, state=GoalState.active, **kwargs):
    now = datetime.now(timezone.utc)
    g = Goal(title=title, goal_type=goal_type, state=state, created_at=now, updated_at=now, **kwargs)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


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


# ── POST /v1/admin/sync/garmin ────────────────────────────────────────────────

def test_garmin_sync_returns_200(test_app, test_db):
    resp = test_app.post("/v1/admin/sync/garmin")
    assert resp.status_code == 200


def test_garmin_sync_response_shape(test_app, test_db):
    data = test_app.post("/v1/admin/sync/garmin").json()
    assert data["status"] == "ok"
    assert "records_synced" in data
    assert "last_sync" in data


def test_garmin_sync_records_synced_is_int(test_app, test_db):
    data = test_app.post("/v1/admin/sync/garmin").json()
    assert isinstance(data["records_synced"], int)


def test_garmin_sync_last_sync_is_iso_string(test_app, test_db):
    from datetime import datetime
    data = test_app.post("/v1/admin/sync/garmin").json()
    # Should parse without error
    datetime.fromisoformat(data["last_sync"])


def test_garmin_sync_idempotent(test_app, test_db):
    # Second call returns 0 records (already synced today)
    test_app.post("/v1/admin/sync/garmin")
    data = test_app.post("/v1/admin/sync/garmin").json()
    assert data["status"] == "ok"
    assert data["records_synced"] == 0


# ── POST /v1/admin/sync/strava ────────────────────────────────────────────────

def test_strava_sync_returns_200(test_app, test_db):
    resp = test_app.post("/v1/admin/sync/strava")
    assert resp.status_code == 200


def test_strava_sync_response_shape(test_app, test_db):
    data = test_app.post("/v1/admin/sync/strava").json()
    assert data["status"] == "ok"
    assert "records_synced" in data
    assert "last_sync" in data


def test_strava_sync_records_synced_is_int(test_app, test_db):
    data = test_app.post("/v1/admin/sync/strava").json()
    assert isinstance(data["records_synced"], int)


def test_strava_sync_last_sync_is_iso_string(test_app, test_db):
    from datetime import datetime
    data = test_app.post("/v1/admin/sync/strava").json()
    datetime.fromisoformat(data["last_sync"])


def test_strava_sync_idempotent(test_app, test_db):
    # Second call returns 0 new records (stub activity already stored)
    test_app.post("/v1/admin/sync/strava")
    data = test_app.post("/v1/admin/sync/strava").json()
    assert data["status"] == "ok"
    assert data["records_synced"] == 0


# ── GET /v1/now — activities_this_week ────────────────────────────────────────

def test_activities_this_week_appears_in_response(test_app, test_db):
    _add_strava_activity(test_db, hours_ago=2)
    data = test_app.get("/v1/now").json()
    assert "activities_this_week" in data
    assert len(data["activities_this_week"]) >= 1


def test_activities_this_week_excludes_last_week(test_app, test_db):
    _add_strava_activity(test_db, hours_ago=2)           # this week
    _add_strava_activity(test_db, hours_ago=8 * 24)      # 8 days ago — last week
    data = test_app.get("/v1/now").json()
    # Only the recent one should be included
    assert len(data["activities_this_week"]) == 1


def test_activities_this_week_shape(test_app, test_db):
    _add_strava_activity(test_db, hours_ago=1, activity_type="Run", distance_km=12.5, tss=95)
    data = test_app.get("/v1/now").json()
    acts = data["activities_this_week"]
    assert len(acts) == 1
    a = acts[0]
    assert "sport_type" in a
    assert "distance_km" in a
    assert "tss" in a
    assert "day_name" in a
    assert a["sport_type"] == "run"
    assert a["distance_km"] == 12.5
    assert a["tss"] == 95


def test_activities_this_week_empty_when_no_activities(test_app, test_db):
    data = test_app.get("/v1/now").json()
    assert data["activities_this_week"] == []


def test_activities_this_week_only_counts_strava_source(test_app, test_db):
    # Manual activity reading should not appear
    _add_reading(test_db, "activity", 1.0, hours_ago=2, source=MetricSource.manual)
    data = test_app.get("/v1/now").json()
    assert data["activities_this_week"] == []


# ── GET /v1/now — goals_snapshot ──────────────────────────────────────────────

def test_goals_snapshot_present(test_app, test_db):
    data = test_app.get("/v1/now").json()
    assert "goals_snapshot" in data


def test_goals_snapshot_perpetual_has_rag(test_app, test_db):
    _make_goal(test_db, "HRV goal", GoalType.perpetual, target_metric_type="hrv", target_min=50.0)
    data = test_app.get("/v1/now").json()
    snap = data["goals_snapshot"]
    perpetual = [g for g in snap if g["goal_type"] == "perpetual"]
    assert len(perpetual) == 1
    assert "rag" in perpetual[0]
    assert perpetual[0]["rag"] in ("green", "amber", "red", "none")


def test_goals_snapshot_achievement_has_days_and_trajectory(test_app, test_db):
    future_date = (date.today() + timedelta(days=30)).isoformat()
    _make_goal(test_db, "Run a marathon", GoalType.achievement, target_date=date.today() + timedelta(days=30))
    data = test_app.get("/v1/now").json()
    snap = data["goals_snapshot"]
    achievement = [g for g in snap if g["goal_type"] == "achievement"]
    assert len(achievement) == 1
    a = achievement[0]
    assert "days_remaining" in a
    assert "trajectory" in a
    assert a["days_remaining"] == 30
    assert a["trajectory"] in ("Ahead", "On track", "Behind", "No data")


def test_goals_snapshot_habit_has_period_count_and_target(test_app, test_db):
    _make_goal(test_db, "Daily run", GoalType.habit, weekly_target=5)
    data = test_app.get("/v1/now").json()
    snap = data["goals_snapshot"]
    habit = [g for g in snap if g["goal_type"] == "habit"]
    assert len(habit) == 1
    h = habit[0]
    assert "this_period_count" in h
    assert "weekly_target" in h
    assert h["this_period_count"] == 0
    assert h["weekly_target"] == 5


def test_goals_snapshot_excludes_terminal_goals(test_app, test_db):
    _make_goal(test_db, "Active goal", GoalType.achievement, state=GoalState.active,
               target_date=date.today() + timedelta(days=10))
    _make_goal(test_db, "Released goal", GoalType.achievement, state=GoalState.released,
               target_date=date.today() + timedelta(days=10))
    data = test_app.get("/v1/now").json()
    snap = data["goals_snapshot"]
    titles = [g["title"] for g in snap]
    assert "Active goal" in titles
    assert "Released goal" not in titles


def test_goals_snapshot_primacy_flagged(test_app, test_db):
    _make_goal(test_db, "Primary goal", GoalType.achievement, state=GoalState.primacy,
               target_date=date.today() + timedelta(days=60))
    data = test_app.get("/v1/now").json()
    snap = data["goals_snapshot"]
    primacy = [g for g in snap if g.get("is_primacy")]
    assert len(primacy) == 1
    assert primacy[0]["title"] == "Primary goal"


def test_goals_snapshot_drifting_state_preserved(test_app, test_db):
    _make_goal(test_db, "Drifting goal", GoalType.achievement, state=GoalState.drifting,
               target_date=date.today() + timedelta(days=60))
    data = test_app.get("/v1/now").json()
    snap = data["goals_snapshot"]
    drifting = [g for g in snap if g["state"] == "drifting"]
    assert len(drifting) == 1


# ── GET /v1/now — general_condition field ─────────────────────────────────────

def test_now_has_general_condition_field(test_app, test_db):
    data = test_app.get("/v1/now").json()
    assert "general_condition" in data


def test_now_general_condition_no_data_when_empty(test_app, test_db):
    data = test_app.get("/v1/now").json()
    assert data["general_condition"] == "No data yet"


def test_now_general_condition_depleted_when_low_sleep(test_app, test_db):
    # Add a Garmin sleep score of 40 (depleted threshold < 50)
    global _reading_id
    _reading_id += 1
    ts = datetime.now(timezone.utc)
    r = MetricReading(
        id=_reading_id,
        timestamp=ts,
        metric_type=MetricType.sleep_score,
        source=MetricSource.garmin,
        value=40.0,
    )
    test_db.add(r)
    test_db.commit()
    data = test_app.get("/v1/now").json()
    assert data["general_condition"] == "Depleted"
