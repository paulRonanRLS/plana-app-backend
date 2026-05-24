"""Unit tests for app/services/capability.py."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.models.goal import Goal, GoalState
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.services.capability import (
    CapabilityBaseline,
    get_capability_baseline,
    infer_goal_activity_type,
)


# ── helpers ────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _goal(title="Run a marathon", description=None):
    return Goal(title=title, description=description, state=GoalState.active)


def _add_activity(db, activity_type, distance_km, moving_time_s=None,
                  normalized_power_w=None, days_ago=1):
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    ts = _now() - timedelta(days=days_ago)
    notes = json.dumps({
        "type": activity_type,
        "distance_km": distance_km,
        "moving_time_s": moving_time_s or 0,
        "normalized_power_w": normalized_power_w,
    })
    r = MetricReading(
        timestamp=ts,
        metric_type=MetricType.activity,
        value=distance_km,
        text_value=activity_type,
        source=MetricSource.strava,
        notes=notes,
    )
    db.add(r)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        r = MetricReading(
            id=max_id + 1,
            timestamp=ts,
            metric_type=MetricType.activity,
            value=distance_km,
            text_value=activity_type,
            source=MetricSource.strava,
            notes=notes,
        )
        db.add(r)
        db.commit()
    return r


def _add_tss(db, tss_value, days_ago=1):
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    ts = _now() - timedelta(days=days_ago)
    r = MetricReading(
        timestamp=ts,
        metric_type=MetricType.tss,
        value=tss_value,
        source=MetricSource.strava,
    )
    db.add(r)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        r = MetricReading(id=max_id + 1, timestamp=ts, metric_type=MetricType.tss,
                          value=tss_value, source=MetricSource.strava)
        db.add(r)
        db.commit()
    return r


# ── infer_goal_activity_type ───────────────────────────────────────────────────

def test_infer_run_from_title():
    assert infer_goal_activity_type(_goal("Run a marathon")) == "run"


def test_infer_run_from_5k():
    assert infer_goal_activity_type(_goal("Complete a 5k race")) == "run"


def test_infer_run_from_description():
    assert infer_goal_activity_type(_goal("Fitness", "Train for a half marathon by October")) == "run"


def test_infer_ride_from_title():
    assert infer_goal_activity_type(_goal("Do a century ride")) == "ride"


def test_infer_ride_from_cycling():
    assert infer_goal_activity_type(_goal("Improve cycling fitness")) == "ride"


def test_infer_ride_from_ftp():
    assert infer_goal_activity_type(_goal("Raise my FTP to 280 watts")) == "ride"


def test_infer_general_fallback():
    assert infer_goal_activity_type(_goal("Write a novel")) == "general"


def test_infer_general_weight():
    assert infer_goal_activity_type(_goal("Lose 5kg")) == "general"


# ── get_capability_baseline — general ─────────────────────────────────────────

def test_general_baseline_returns_immediately(test_db):
    b = get_capability_baseline(test_db, "general")
    assert b.goal_type == "general"
    assert b.long_run_km is None
    assert b.weekly_volume_km is None


def test_empty_db_run_returns_none_metrics(test_db):
    b = get_capability_baseline(test_db, "run")
    assert b.goal_type == "run"
    assert b.long_run_km is None
    assert b.weekly_volume_km is None
    assert b.avg_pace_min_per_km is None
    assert b.run_count == 0


def test_empty_db_ride_returns_none_metrics(test_db):
    b = get_capability_baseline(test_db, "ride")
    assert b.goal_type == "ride"
    assert b.longest_ride_km is None
    assert b.ftp_estimate_w is None
    assert b.weekly_tss is None
    assert b.ride_count == 0


# ── get_capability_baseline — running ─────────────────────────────────────────

def test_run_baseline_counts_runs(test_db):
    _add_activity(test_db, "Run", 10.0, moving_time_s=3000, days_ago=5)
    _add_activity(test_db, "Run", 8.0, moving_time_s=2400, days_ago=10)
    b = get_capability_baseline(test_db, "run")
    assert b.run_count == 2


def test_run_baseline_long_run_uses_last_28_days(test_db):
    _add_activity(test_db, "Run", 20.0, days_ago=5)   # recent — counts
    _add_activity(test_db, "Run", 30.0, days_ago=60)  # older than 28d — excluded from long run
    b = get_capability_baseline(test_db, "run")
    assert b.long_run_km == pytest.approx(20.0, abs=0.1)


def test_run_baseline_weekly_volume_uses_90_days(test_db):
    # 4 runs of 10km each, spread over last 40 days (within 90d window)
    for d in [5, 12, 19, 26]:
        _add_activity(test_db, "Run", 10.0, days_ago=d)
    b = get_capability_baseline(test_db, "run")
    # 40km over ~12.86 weeks = ~3.1 km/week
    assert b.weekly_volume_km is not None
    assert b.weekly_volume_km > 0


def test_run_baseline_avg_pace_calculated(test_db):
    # 10km in 3000s = 5 min/km
    _add_activity(test_db, "Run", 10.0, moving_time_s=3000, days_ago=3)
    b = get_capability_baseline(test_db, "run")
    assert b.avg_pace_min_per_km is not None
    assert b.avg_pace_min_per_km == pytest.approx(5.0, abs=0.1)


def test_run_baseline_excludes_ride_activities(test_db):
    _add_activity(test_db, "Ride", 50.0, days_ago=3)
    _add_activity(test_db, "Run", 10.0, moving_time_s=3000, days_ago=5)
    b = get_capability_baseline(test_db, "run")
    assert b.run_count == 1


def test_run_baseline_ignores_old_activities(test_db):
    # 95 days ago — outside the 90-day window
    _add_activity(test_db, "Run", 25.0, days_ago=95)
    b = get_capability_baseline(test_db, "run")
    assert b.run_count == 0
    assert b.long_run_km is None


# ── get_capability_baseline — cycling ─────────────────────────────────────────

def test_ride_baseline_counts_rides(test_db):
    _add_activity(test_db, "Ride", 80.0, days_ago=3)
    _add_activity(test_db, "Ride", 50.0, days_ago=8)
    b = get_capability_baseline(test_db, "ride")
    assert b.ride_count == 2


def test_ride_baseline_longest_ride(test_db):
    _add_activity(test_db, "Ride", 80.0, days_ago=5)
    _add_activity(test_db, "Ride", 120.0, days_ago=10)
    _add_activity(test_db, "Ride", 60.0, days_ago=15)
    b = get_capability_baseline(test_db, "ride")
    assert b.longest_ride_km == pytest.approx(120.0, abs=0.1)


def test_ride_baseline_ftp_estimate_from_power(test_db):
    # Max NP 280W → FTP estimate = 280 * 0.95 = 266W
    _add_activity(test_db, "Ride", 80.0, normalized_power_w=280.0, days_ago=5)
    _add_activity(test_db, "Ride", 60.0, normalized_power_w=250.0, days_ago=10)
    b = get_capability_baseline(test_db, "ride")
    assert b.ftp_estimate_w == pytest.approx(266.0, abs=1.0)


def test_ride_baseline_weekly_tss_from_tss_readings(test_db):
    _add_activity(test_db, "Ride", 80.0, days_ago=3)
    _add_tss(test_db, 100.0, days_ago=3)
    _add_tss(test_db, 80.0, days_ago=10)
    b = get_capability_baseline(test_db, "ride")
    assert b.weekly_tss is not None
    assert b.weekly_tss > 0


def test_ride_baseline_excludes_run_activities(test_db):
    _add_activity(test_db, "Run", 10.0, days_ago=3)
    _add_activity(test_db, "Ride", 80.0, days_ago=5)
    b = get_capability_baseline(test_db, "ride")
    assert b.ride_count == 1


def test_ride_baseline_no_ftp_without_power_data(test_db):
    # normalized_power_w is None — no FTP estimate
    _add_activity(test_db, "Ride", 80.0, normalized_power_w=None, days_ago=3)
    b = get_capability_baseline(test_db, "ride")
    assert b.ftp_estimate_w is None
