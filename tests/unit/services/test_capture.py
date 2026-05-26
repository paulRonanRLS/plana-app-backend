"""Unit tests for app/services/capture.py."""

from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.services.capture import (
    _extract_number,
    _parse_metric,
    record_illness,
    record_metric,
    record_physical_state,
    record_progress,
)


# ── record_progress ────────────────────────────────────────────────────────────

def test_record_progress_writes_habit_log(test_db):
    r = record_progress(test_db, "just cooked dinner")
    assert r.metric_type == MetricType.habit_log


def test_record_progress_stores_text(test_db):
    r = record_progress(test_db, "just cooked dinner")
    assert r.text_value == "just cooked dinner"


def test_record_progress_source_is_telegram(test_db):
    r = record_progress(test_db, "ran 5k")
    assert r.source == MetricSource.telegram


def test_record_progress_persists_to_db(test_db):
    record_progress(test_db, "finished chapter 3")
    rows = test_db.query(MetricReading).filter(
        MetricReading.metric_type == MetricType.habit_log
    ).all()
    assert len(rows) == 1


def test_record_progress_truncates_long_text(test_db):
    long_text = "x" * 600
    r = record_progress(test_db, long_text)
    assert len(r.text_value) == 500


# ── record_physical_state ──────────────────────────────────────────────────────

def test_record_physical_state_type(test_db):
    r = record_physical_state(test_db, "my calves are sore")
    assert r.metric_type == MetricType.physical_state


def test_record_physical_state_stores_text(test_db):
    r = record_physical_state(test_db, "left knee niggle")
    assert r.text_value == "left knee niggle"


def test_record_physical_state_source(test_db):
    r = record_physical_state(test_db, "sore legs")
    assert r.source == MetricSource.telegram


# ── record_illness ─────────────────────────────────────────────────────────────

def test_record_illness_type(test_db):
    r = record_illness(test_db, "feeling sick, sore throat")
    assert r.metric_type == MetricType.illness_log


def test_record_illness_stores_text(test_db):
    r = record_illness(test_db, "finally recovering from that cold")
    assert "recovering" in r.text_value


# ── record_metric ──────────────────────────────────────────────────────────────

def test_record_metric_weight(test_db):
    r = record_metric(test_db, "weight 74.5kg this morning")
    assert r.metric_type == MetricType.weight
    assert r.value == 74.5


def test_record_metric_weight_lb(test_db):
    r = record_metric(test_db, "164 lbs today")
    assert r.metric_type == MetricType.weight
    assert r.value == 164.0


def test_record_metric_alcohol_units(test_db):
    r = record_metric(test_db, "had 3 units last night")
    assert r.metric_type == MetricType.alcohol_units
    assert r.value == 3.0


def test_record_metric_alcohol_drinks(test_db):
    r = record_metric(test_db, "2 glasses of wine")
    assert r.metric_type == MetricType.alcohol_units
    assert r.value == 2.0


def test_record_metric_fallback_to_habit_log(test_db):
    r = record_metric(test_db, "did something unmeasured")
    assert r.metric_type == MetricType.habit_log


def test_record_metric_no_number_value_is_none(test_db):
    r = record_metric(test_db, "had some drinks")
    assert r.metric_type == MetricType.alcohol_units
    assert r.value is None


def test_record_metric_stores_original_text(test_db):
    r = record_metric(test_db, "weight 74.5kg this morning")
    assert r.text_value == "weight 74.5kg this morning"


# ── _parse_metric ──────────────────────────────────────────────────────────────

def test_parse_metric_weight_kg():
    t, v = _parse_metric("74.5kg")
    assert t == MetricType.weight
    assert v == 74.5


def test_parse_metric_alcohol_units():
    t, v = _parse_metric("3 units")
    assert t == MetricType.alcohol_units
    assert v == 3.0


def test_parse_metric_fallback():
    t, v = _parse_metric("something random")
    assert t == MetricType.habit_log


# ── _extract_number ────────────────────────────────────────────────────────────

def test_extract_number_integer():
    assert _extract_number("3 units") == 3.0


def test_extract_number_decimal():
    assert _extract_number("74.5kg") == 74.5


def test_extract_number_none():
    assert _extract_number("no numbers here") is None


def test_extract_number_first_match():
    assert _extract_number("had 2 out of 3 drinks") == 2.0
