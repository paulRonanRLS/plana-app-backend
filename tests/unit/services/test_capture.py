"""Unit tests for app/services/capture.py."""

import json
from datetime import datetime, timezone

from app.models.goal import Goal, GoalState
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.services.capture import (
    _extract_number,
    _parse_metric,
    match_goal_title,
    record_illness,
    record_metric,
    record_physical_state,
    record_progress,
)


# ── match_goal_title ───────────────────────────────────────────────────────────

def _make_goal(title: str, state: GoalState = GoalState.active) -> Goal:
    return Goal(title=title, state=state,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc))


def test_match_goal_title_explicit_name():
    goals = [_make_goal("Cooking")]
    result = match_goal_title("cooked dinner for my cooking goal", goals)
    assert result is not None
    assert result.title == "Cooking"


def test_match_goal_title_no_match():
    goals = [_make_goal("Cooking")]
    result = match_goal_title("went for a run today", goals)
    assert result is None


def test_match_goal_title_case_insensitive():
    goals = [_make_goal("Half Marathon")]
    result = match_goal_title("Training for the half marathon today", goals)
    assert result is not None


def test_match_goal_title_returns_first_match():
    goals = [_make_goal("Cooking"), _make_goal("Running")]
    result = match_goal_title("did some cooking and running", goals)
    assert result.title == "Cooking"


def test_match_goal_title_word_boundary_no_partial():
    # "Run" should NOT match inside "running" (different word form is fine due to boundary)
    goals = [_make_goal("Run")]
    result = match_goal_title("went running today", goals)
    # "run" word boundary: "running" does not contain standalone "run" → no match
    assert result is None


def test_match_goal_title_word_boundary_exact():
    goals = [_make_goal("Run")]
    result = match_goal_title("did my run today", goals)
    assert result is not None


def test_match_goal_title_multi_word_title():
    goals = [_make_goal("Half Marathon")]
    result = match_goal_title("prep for half marathon race", goals)
    assert result is not None


def test_match_goal_title_empty_goals():
    assert match_goal_title("cooked dinner", []) is None


def test_match_goal_title_empty_text():
    goals = [_make_goal("Cooking")]
    assert match_goal_title("", goals) is None


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


def test_record_progress_with_goal_id_stores_id_in_text_value(test_db):
    r = record_progress(test_db, "cooked dinner for cooking goal", goal_id=7)
    assert r.text_value == "7"


def test_record_progress_with_goal_id_stores_text_in_notes(test_db):
    r = record_progress(test_db, "cooked dinner", goal_id=7)
    notes = json.loads(r.notes)
    assert notes["goal_id"] == 7
    assert "cooked dinner" in notes["text"]


def test_record_progress_with_goal_id_is_habit_log(test_db):
    r = record_progress(test_db, "cooked dinner", goal_id=3)
    assert r.metric_type == MetricType.habit_log


def test_record_progress_without_goal_id_unchanged(test_db):
    r = record_progress(test_db, "did something")
    assert r.text_value == "did something"
    assert r.notes is None


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
