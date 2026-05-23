"""Unit tests for app/ingestion/garmin.py — all in stub mode (GARMIN_ENABLED=false)."""

from datetime import datetime, timezone

import pytest

from app.ingestion.garmin import (
    _has_today_data,
    _persist,
    _stub_reading_dicts,
    sync_garmin,
)
from app.models.metric_reading import MetricReading, MetricSource, MetricType


# ── _stub_reading_dicts ────────────────────────────────────────────────────────

def test_stub_produces_six_readings():
    readings = _stub_reading_dicts()
    assert len(readings) == 6


def test_stub_covers_expected_metric_types():
    types = {r["metric_type"] for r in _stub_reading_dicts()}
    assert MetricType.sleep_score in types
    assert MetricType.sleep_duration_hours in types
    assert MetricType.hrv in types
    assert MetricType.resting_hr in types
    assert MetricType.body_battery in types
    assert MetricType.stress in types


def test_stub_all_have_timestamps():
    for r in _stub_reading_dicts():
        assert isinstance(r["timestamp"], datetime)
        assert r["timestamp"].tzinfo is not None


def test_stub_all_have_positive_values():
    for r in _stub_reading_dicts():
        assert r["value"] is not None
        assert r["value"] > 0


# ── _has_today_data ────────────────────────────────────────────────────────────

def test_has_today_data_false_when_empty(test_db):
    assert _has_today_data(test_db) is False


def test_has_today_data_true_after_sync(test_db):
    _persist(test_db, _stub_reading_dicts())
    assert _has_today_data(test_db) is True


def test_has_today_data_ignores_other_sources(test_db):
    from app.ingestion.strava import _persist as strava_persist
    strava_persist(test_db, [{
        "timestamp": datetime.now(timezone.utc),
        "metric_type": MetricType.tss,
        "value": 100.0,
        "source": MetricSource.strava,
    }])
    assert _has_today_data(test_db) is False


# ── sync_garmin (stub mode) ────────────────────────────────────────────────────

def test_sync_garmin_stub_saves_rows(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    rows = sync_garmin(test_db)
    assert len(rows) == 6
    assert all(isinstance(r, MetricReading) for r in rows)


def test_sync_garmin_stub_source_is_garmin(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    rows = sync_garmin(test_db)
    assert all(r.source == MetricSource.garmin for r in rows)


def test_sync_garmin_stub_idempotent(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    first = sync_garmin(test_db)
    second = sync_garmin(test_db)
    assert len(first) == 6
    assert len(second) == 0  # skipped — data already present


def test_sync_garmin_skips_when_data_exists(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    _persist(test_db, _stub_reading_dicts())
    rows = sync_garmin(test_db)
    assert rows == []


def test_sync_garmin_persisted_rows_in_db(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    sync_garmin(test_db)
    count = test_db.query(MetricReading).filter(
        MetricReading.source == MetricSource.garmin
    ).count()
    assert count == 6


def test_sync_garmin_sleep_score_in_range(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    rows = sync_garmin(test_db)
    sleep_score = next(r for r in rows if r.metric_type == MetricType.sleep_score)
    assert 0 <= sleep_score.value <= 100


def test_sync_garmin_hrv_plausible(test_db, monkeypatch):
    monkeypatch.setenv("GARMIN_ENABLED", "false")
    from app.config import get_settings
    get_settings.cache_clear()

    rows = sync_garmin(test_db)
    hrv = next(r for r in rows if r.metric_type == MetricType.hrv)
    assert 20 <= hrv.value <= 200


# ── _persist ───────────────────────────────────────────────────────────────────

def test_persist_empty_list(test_db):
    result = _persist(test_db, [])
    assert result == []


def test_persist_saves_correct_count(test_db):
    dicts = _stub_reading_dicts()
    rows = _persist(test_db, dicts)
    assert len(rows) == len(dicts)
    assert test_db.query(MetricReading).count() == len(dicts)
