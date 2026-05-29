"""Unit tests for app/services/capture.py."""

import json
from datetime import datetime, timezone

from datetime import datetime, timezone

from app.models.goal import Goal, GoalState
from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.models.milestone import Milestone, MilestoneState
from app.models.sacrifice import ResourceType, Sacrifice
from app.services.capture import (
    _extract_number,
    _parse_metric,
    extract_resource_from_text,
    extract_target_state_from_text,
    match_goal_by_keywords,
    match_goal_title,
    match_milestone_title,
    record_illness,
    record_metric,
    record_physical_state,
    record_progress,
    record_sacrifice,
)


# ── match_goal_title ───────────────────────────────────────────────────────────

def _make_goal(title: str, state: GoalState = GoalState.active, keywords: str | None = None) -> Goal:
    now = datetime.now(timezone.utc)
    return Goal(title=title, state=state, capture_keywords=keywords,
                created_at=now, updated_at=now)


def _make_milestone(title: str, state: MilestoneState = MilestoneState.pending) -> Milestone:
    now = datetime.now(timezone.utc)
    return Milestone(title=title, state=state, sequence=1, created_at=now, updated_at=now)


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


# ── match_goal_by_keywords ─────────────────────────────────────────────────────

def test_match_goal_by_keywords_finds_keyword_match():
    import json
    goal = _make_goal("Half Marathon", keywords=json.dumps(["long run", "marathon"]))
    result = match_goal_by_keywords("did my long run this morning", [goal])
    assert result is not None
    assert result.title == "Half Marathon"


def test_match_goal_by_keywords_no_keywords_on_goal():
    goal = _make_goal("Half Marathon")  # no capture_keywords
    result = match_goal_by_keywords("ran 18km this morning", [goal])
    assert result is None


def test_match_goal_by_keywords_empty_list():
    assert match_goal_by_keywords("anything", []) is None


def test_match_goal_by_keywords_case_insensitive():
    import json
    goal = _make_goal("Cycling", keywords=json.dumps(["Ride", "Bike"]))
    result = match_goal_by_keywords("did a ride today", [goal])
    assert result is not None


def test_match_goal_by_keywords_word_boundary():
    import json
    goal = _make_goal("Run", keywords=json.dumps(["run"]))
    # "running" should NOT match keyword "run" at word boundary
    result = match_goal_by_keywords("went running this morning", [goal])
    assert result is None


def test_keywords_tried_before_title_in_resolution_scenario():
    """Keywords should resolve when the goal title alone wouldn't match."""
    import json
    goal = _make_goal("Half Marathon", keywords=json.dumps(["long run"]))
    # "long run" matches via keywords even though "Half Marathon" is not in text
    by_kw = match_goal_by_keywords("did my long run", [goal])
    by_title = match_goal_title("did my long run", [goal])
    assert by_kw is not None   # keyword match succeeds
    assert by_title is None    # title match fails — confirms Fix 3 is needed


# ── record_sacrifice ───────────────────────────────────────────────────────────

def test_record_sacrifice_writes_row(test_db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    g = Goal(title="Run", state=GoalState.active, created_at=now, updated_at=now)
    test_db.add(g)
    test_db.commit()
    test_db.refresh(g)

    s = record_sacrifice(test_db, g.id, ResourceType.time, "skipped my run for work")
    assert s.id is not None
    assert s.goal_id == g.id
    assert s.resource == ResourceType.time


def test_record_sacrifice_correct_resource(test_db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    g = Goal(title="Training", state=GoalState.active, created_at=now, updated_at=now)
    test_db.add(g)
    test_db.commit()
    test_db.refresh(g)

    s = record_sacrifice(test_db, g.id, ResourceType.recovery, "too tired to train")
    assert s.resource == ResourceType.recovery


def test_record_sacrifice_stores_notes(test_db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    g = Goal(title="Training", state=GoalState.active, created_at=now, updated_at=now)
    test_db.add(g)
    test_db.commit()
    test_db.refresh(g)

    s = record_sacrifice(test_db, g.id, ResourceType.attention, "too distracted today")
    assert "distracted" in s.notes


def test_record_sacrifice_persists_to_db(test_db):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    g = Goal(title="Run", state=GoalState.active, created_at=now, updated_at=now)
    test_db.add(g)
    test_db.commit()
    test_db.refresh(g)

    record_sacrifice(test_db, g.id, ResourceType.time, "skipped for work")
    count = test_db.query(Sacrifice).filter(Sacrifice.goal_id == g.id).count()
    assert count == 1


# ── extract_resource_from_text ─────────────────────────────────────────────────

def test_extract_resource_work_is_time():
    assert extract_resource_from_text("had to skip because of work") == ResourceType.time


def test_extract_resource_meeting_is_time():
    assert extract_resource_from_text("meeting ran long") == ResourceType.time


def test_extract_resource_tired_is_recovery():
    assert extract_resource_from_text("was too tired to train") == ResourceType.recovery


def test_extract_resource_exhausted_is_recovery():
    assert extract_resource_from_text("felt completely exhausted") == ResourceType.recovery


def test_extract_resource_distracted_is_attention():
    assert extract_resource_from_text("too distracted to focus") == ResourceType.attention


def test_extract_resource_motivation_is_willpower():
    assert extract_resource_from_text("just couldn't find the motivation") == ResourceType.willpower


def test_extract_resource_default_is_time():
    assert extract_resource_from_text("something happened") == ResourceType.time


# ── match_milestone_title ──────────────────────────────────────────────────────

def test_match_milestone_title_finds_match():
    m = _make_milestone("Foundation")
    result = match_milestone_title("just finished my foundation milestone", [m])
    assert result is not None
    assert result.title == "Foundation"


def test_match_milestone_title_case_insensitive():
    m = _make_milestone("Long Run")
    result = match_milestone_title("completed the long run block", [m])
    assert result is not None


def test_match_milestone_title_no_match():
    m = _make_milestone("Foundation")
    result = match_milestone_title("completed something else entirely", [m])
    assert result is None


def test_match_milestone_title_empty_list():
    assert match_milestone_title("completed my milestone", []) is None


def test_match_milestone_title_returns_first():
    m1 = _make_milestone("Foundation")
    m2 = _make_milestone("Build")
    result = match_milestone_title("done with foundation and build", [m1, m2])
    assert result.title == "Foundation"


# ── extract_target_state_from_text ─────────────────────────────────────────────

def test_extract_target_state_primacy():
    assert extract_target_state_from_text("set as my plana") == "primacy"


def test_extract_target_state_primacy_keyword():
    assert extract_target_state_from_text("make this my top priority") == "primacy"


def test_extract_target_state_subordinate():
    assert extract_target_state_from_text("put it in the background") == "subordinate"


def test_extract_target_state_active():
    assert extract_target_state_from_text("back to active please") == "active"


def test_extract_target_state_unknown_returns_none():
    assert extract_target_state_from_text("change something about the goal") is None
