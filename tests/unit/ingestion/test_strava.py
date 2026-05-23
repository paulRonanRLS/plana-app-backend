"""Unit tests for app/ingestion/strava.py — all in stub mode (STRAVA_ENABLED=false)."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.ingestion.strava import (
    _activity_already_stored,
    _activity_to_rows,
    _calculate_tss,
    _stub_activity_dicts,
    sync_strava,
)
from app.models.metric_reading import MetricReading, MetricSource, MetricType


# ── _calculate_tss ─────────────────────────────────────────────────────────────

def test_tss_1_hour_at_ftp():
    """1 hour at FTP (IF=1.0) should give TSS=100."""
    tss = _calculate_tss(moving_time_s=3600, normalized_power_w=250, ftp_w=250)
    assert abs(tss - 100.0) < 0.01


def test_tss_1_hour_at_half_ftp():
    """1 hour at half FTP (IF=0.5) should give TSS=25."""
    tss = _calculate_tss(moving_time_s=3600, normalized_power_w=125, ftp_w=250)
    assert abs(tss - 25.0) < 0.01


def test_tss_scales_with_duration():
    tss_1h = _calculate_tss(3600, 200, 250)
    tss_2h = _calculate_tss(7200, 200, 250)
    assert abs(tss_2h - tss_1h * 2) < 0.01


def test_tss_positive():
    assert _calculate_tss(3600, 200, 250) > 0


# ── _stub_activity_dicts ───────────────────────────────────────────────────────

def test_stub_returns_at_least_one_activity():
    assert len(_stub_activity_dicts()) >= 1


def test_stub_activity_has_required_keys():
    required = {"strava_id", "timestamp", "activity_type", "distance_km",
                "moving_time_s", "elapsed_time_s"}
    for activity in _stub_activity_dicts():
        assert required.issubset(activity.keys())


def test_stub_activity_timestamp_is_aware():
    for a in _stub_activity_dicts():
        assert a["timestamp"].tzinfo is not None


def test_stub_activity_type_is_string():
    for a in _stub_activity_dicts():
        assert isinstance(a["activity_type"], str)
        assert len(a["activity_type"]) > 0


# ── _activity_to_rows ──────────────────────────────────────────────────────────

def _make_activity(tss=None, activity_type="Run", distance_km=10.0):
    return {
        "strava_id": 12345,
        "name": "Morning run",
        "timestamp": datetime.now(timezone.utc),
        "activity_type": activity_type,
        "distance_km": distance_km,
        "moving_time_s": 3600,
        "elapsed_time_s": 3700,
        "avg_hr": 148,
        "max_hr": 170,
        "normalized_power_w": None,
        "tss": tss,
    }


def test_activity_to_rows_produces_one_row_without_tss():
    rows = _activity_to_rows(_make_activity(tss=None))
    assert len(rows) == 1
    assert rows[0]["metric_type"] == MetricType.activity


def test_activity_to_rows_produces_two_rows_with_tss():
    rows = _activity_to_rows(_make_activity(tss=85.0))
    types = {r["metric_type"] for r in rows}
    assert MetricType.activity in types
    assert MetricType.tss in types


def test_activity_row_notes_contains_strava_id():
    rows = _activity_to_rows(_make_activity())
    activity_row = next(r for r in rows if r["metric_type"] == MetricType.activity)
    notes = json.loads(activity_row["notes"])
    assert notes["strava_id"] == 12345


def test_activity_row_text_value_is_type():
    rows = _activity_to_rows(_make_activity(activity_type="Ride"))
    activity_row = next(r for r in rows if r["metric_type"] == MetricType.activity)
    assert activity_row["text_value"] == "Ride"


def test_activity_row_value_is_distance():
    rows = _activity_to_rows(_make_activity(distance_km=42.2))
    activity_row = next(r for r in rows if r["metric_type"] == MetricType.activity)
    assert activity_row["value"] == 42.2


def test_tss_row_value_matches():
    rows = _activity_to_rows(_make_activity(tss=77.5))
    tss_row = next(r for r in rows if r["metric_type"] == MetricType.tss)
    assert tss_row["value"] == 77.5


# ── _activity_already_stored ───────────────────────────────────────────────────

def test_activity_not_stored_initially(test_db):
    assert _activity_already_stored(test_db, strava_id=99999) is False


def test_activity_stored_after_sync(test_db, monkeypatch):
    monkeypatch.setenv("STRAVA_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    sync_strava(test_db)
    strava_id = _stub_activity_dicts()[0]["strava_id"]
    assert _activity_already_stored(test_db, strava_id) is True


# ── sync_strava (stub mode) ────────────────────────────────────────────────────

def test_sync_strava_stub_saves_rows(test_db, monkeypatch):
    monkeypatch.setenv("STRAVA_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    rows = sync_strava(test_db)
    assert len(rows) >= 1


def test_sync_strava_stub_activity_row_present(test_db, monkeypatch):
    monkeypatch.setenv("STRAVA_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    sync_strava(test_db)
    count = test_db.query(MetricReading).filter(
        MetricReading.metric_type == MetricType.activity,
        MetricReading.source == MetricSource.strava,
    ).count()
    assert count >= 1


def test_sync_strava_stub_source_is_strava(test_db, monkeypatch):
    monkeypatch.setenv("STRAVA_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    rows = sync_strava(test_db)
    assert all(r.source == MetricSource.strava for r in rows)


def test_sync_strava_stub_idempotent(test_db, monkeypatch):
    monkeypatch.setenv("STRAVA_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    first = sync_strava(test_db)
    second = sync_strava(test_db)
    assert len(first) >= 1
    assert len(second) == 0  # skipped — already stored


def test_sync_strava_activity_notes_valid_json(test_db, monkeypatch):
    monkeypatch.setenv("STRAVA_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    sync_strava(test_db)
    activity_row = test_db.query(MetricReading).filter(
        MetricReading.metric_type == MetricType.activity
    ).first()
    assert activity_row is not None
    notes = json.loads(activity_row.notes)
    assert "strava_id" in notes
    assert "type" in notes
