"""Unit tests for app/services/activity.py."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.ingestion.garmin import _persist as garmin_persist
from app.ingestion.strava import _persist as strava_persist
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.services.activity import (
    _parse_activity_type,
    parse_date_reference,
    query_activities,
)


# ── parse_date_reference ───────────────────────────────────────────────────────

def _today():
    return datetime(2026, 5, 23, 12, 0, 0, tzinfo=timezone.utc)  # Saturday


def test_parse_yesterday():
    start, end = parse_date_reference("what was my ride yesterday?", today=_today())
    assert start.date() == _today().date() - timedelta(days=1)
    assert end.date() == start.date()


def test_parse_today():
    start, end = parse_date_reference("show me today's workout", today=_today())
    assert start.date() == _today().date()


def test_parse_last_week():
    start, end = parse_date_reference("how far did I run last week", today=_today())
    # 2026-05-23 is Saturday (weekday=5), last Monday = 2026-05-11
    assert start.weekday() == 0  # Monday
    assert end.weekday() == 6    # Sunday
    assert (end.date() - start.date()).days == 6


def test_parse_weekday_sunday():
    # today = Saturday 2026-05-23; most recent Sunday = 2026-05-17
    start, end = parse_date_reference("what was my ride on Sunday", today=_today())
    assert start.date().weekday() == 6  # Sunday
    assert start.date() == datetime(2026, 5, 17, tzinfo=timezone.utc).date()


def test_parse_weekday_monday():
    # most recent Monday before Saturday = 2026-05-18
    start, end = parse_date_reference("my session last Monday", today=_today())
    assert start.date().weekday() == 0
    assert start.date() == datetime(2026, 5, 18, tzinfo=timezone.utc).date()


def test_parse_iso_date():
    start, end = parse_date_reference("what about 2026-05-20?", today=_today())
    assert start.date() == datetime(2026, 5, 20, tzinfo=timezone.utc).date()


def test_parse_this_morning():
    start, end = parse_date_reference("how was my run this morning", today=_today())
    assert start.date() == _today().date()


def test_parse_morning_only():
    start, end = parse_date_reference("my morning workout", today=_today())
    assert start.date() == _today().date()


def test_parse_default_falls_back_to_yesterday():
    # No temporal marker — should default to yesterday
    start, end = parse_date_reference("show me my ride", today=_today())
    assert start.date() == (_today().date() - timedelta(days=1))


def test_parse_start_before_end():
    start, end = parse_date_reference("yesterday", today=_today())
    assert start < end


def test_parse_utc_timezone():
    start, end = parse_date_reference("yesterday", today=_today())
    assert start.tzinfo is not None
    assert end.tzinfo is not None


# ── _parse_activity_type ───────────────────────────────────────────────────────

def test_parse_activity_type_ride():
    assert _parse_activity_type("what was my ride on Sunday") == "ride"


def test_parse_activity_type_run():
    assert _parse_activity_type("how far did I run last week") == "run"


def test_parse_activity_type_swim():
    assert _parse_activity_type("how was my swim yesterday") == "swim"


def test_parse_activity_type_none_for_generic():
    assert _parse_activity_type("what was my workout yesterday") is None


def test_parse_activity_type_cycled():
    assert _parse_activity_type("how far did I cycle yesterday") == "ride"


# ── query_activities ───────────────────────────────────────────────────────────

def _make_activity_row(db, name, sport_type, distance_m, moving_time_s, ts=None):
    if ts is None:
        ts = datetime.now(timezone.utc)
    notes = json.dumps({
        "name": name,
        "sport_type": sport_type,
        "distance_m": distance_m,
        "moving_time_s": moving_time_s,
        "elapsed_time_s": moving_time_s,
        "strava_id": 12345,
    })
    strava_persist(db, [{
        "timestamp": ts,
        "metric_type": MetricType.activity,
        "value": distance_m,
        "source": MetricSource.strava,
        "notes": notes,
    }])


def test_query_activities_empty(test_db):
    start = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 23, 59, 59, tzinfo=timezone.utc)
    result = query_activities(test_db, start, end)
    assert result == []


def test_query_activities_finds_in_range(test_db):
    ts = datetime(2026, 5, 22, 8, 30, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Morning Run", "Run", 10200, 3180, ts)

    start = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 23, 59, 59, tzinfo=timezone.utc)
    result = query_activities(test_db, start, end)
    assert len(result) == 1
    assert result[0]["name"] == "Morning Run"


def test_query_activities_excludes_outside_range(test_db):
    ts = datetime(2026, 5, 21, 8, 0, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Old Run", "Run", 5000, 1800, ts)

    start = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 23, 59, 59, tzinfo=timezone.utc)
    result = query_activities(test_db, start, end)
    assert result == []


def test_query_activities_filters_by_type_run(test_db):
    ts = datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Morning Run", "Run", 10200, 3180, ts)
    ts2 = datetime(2026, 5, 22, 10, 0, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Afternoon Ride", "Ride", 40000, 5400, ts2)

    start = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 23, 59, 59, tzinfo=timezone.utc)
    result = query_activities(test_db, start, end, activity_type="run")
    assert len(result) == 1
    assert result[0]["name"] == "Morning Run"


def test_query_activities_no_type_filter_returns_all(test_db):
    ts = datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Morning Run", "Run", 10200, 3180, ts)
    ts2 = datetime(2026, 5, 22, 10, 0, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Afternoon Ride", "Ride", 40000, 5400, ts2)

    start = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 23, 59, 59, tzinfo=timezone.utc)
    result = query_activities(test_db, start, end)
    assert len(result) == 2


def test_query_activities_returns_timestamp(test_db):
    ts = datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc)
    _make_activity_row(test_db, "Morning Run", "Run", 10200, 3180, ts)

    start = datetime(2026, 5, 22, 0, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 22, 23, 59, 59, tzinfo=timezone.utc)
    result = query_activities(test_db, start, end)
    assert result[0]["timestamp"] is not None
