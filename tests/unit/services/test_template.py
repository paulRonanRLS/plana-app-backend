"""Unit tests for app/services/template.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.services.template import (
    _percentile,
    build_goal_from_template,
    get_template,
    list_templates_by_category,
    load_templates,
    suggest_target_range,
)


# ── load_templates ─────────────────────────────────────────────────────────────

def test_load_templates_returns_dict():
    data = load_templates()
    assert isinstance(data, dict)
    assert "categories" in data


def test_load_templates_has_categories():
    data = load_templates()
    assert len(data["categories"]) >= 5


def test_load_templates_version_present():
    data = load_templates()
    assert data.get("version") is not None


# ── list_templates_by_category ────────────────────────────────────────────────

def test_list_by_category_returns_all_categories():
    cats = list_templates_by_category()
    assert "health_foundation" in cats
    assert "training_running" in cats
    assert "training_cycling" in cats
    assert "training_strength" in cats
    assert "habits" in cats


def test_list_by_category_structure():
    cats = list_templates_by_category()
    for cat_id, cat in cats.items():
        assert "id" in cat
        assert "label" in cat
        assert "templates" in cat
        assert isinstance(cat["templates"], list)


def test_health_foundation_has_sleep_quality():
    cats = list_templates_by_category()
    tmpl_ids = [t["id"] for t in cats["health_foundation"]["templates"]]
    assert "sleep_quality" in tmpl_ids


def test_training_running_has_half_marathon():
    cats = list_templates_by_category()
    tmpl_ids = [t["id"] for t in cats["training_running"]["templates"]]
    assert "race_half_marathon" in tmpl_ids


def test_habits_has_cooking():
    cats = list_templates_by_category()
    tmpl_ids = [t["id"] for t in cats["habits"]["templates"]]
    assert "cooking_frequency" in tmpl_ids


# ── get_template ───────────────────────────────────────────────────────────────

def test_get_template_found():
    t = get_template("sleep_quality")
    assert t is not None
    assert t["id"] == "sleep_quality"


def test_get_template_not_found():
    assert get_template("nonexistent_template_xyz") is None


def test_get_template_includes_category():
    t = get_template("sleep_quality")
    assert t["category_id"] == "health_foundation"


def test_get_template_has_required_fields():
    t = get_template("sleep_quality")
    assert t["goal_type"] == "perpetual"
    assert t["metric"] == "sleep_score"
    assert t["direction"] == "higher"
    assert t["default_min"] == 72
    assert t["default_max"] == 100


def test_get_template_race_has_capability_fields():
    t = get_template("race_half_marathon")
    assert isinstance(t.get("capability_fields"), list)
    assert len(t["capability_fields"]) > 0
    field_ids = [f["id"] for f in t["capability_fields"]]
    assert "long_run_km" in field_ids


def test_get_template_race_has_milestone_phases():
    t = get_template("race_half_marathon")
    phases = t.get("milestone_phases", [])
    assert len(phases) >= 4
    assert any("Race day" in p for p in phases)


def test_get_template_habit_has_capture_keywords():
    t = get_template("cooking_frequency")
    assert isinstance(t.get("capture_keywords"), list)
    assert len(t["capture_keywords"]) > 0


def test_get_template_habit_fields():
    t = get_template("cooking_frequency")
    assert t["goal_type"] == "habit"
    assert t["habit_type"] == "count"
    assert t["habit_period"] == "week"
    assert t["default_target"] == 5


# ── _percentile ───────────────────────────────────────────────────────────────

def test_percentile_median():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert _percentile(data, 50) == pytest.approx(3.0)


def test_percentile_p10():
    data = list(range(1, 101))
    assert _percentile(data, 10) == pytest.approx(10.9)


def test_percentile_empty():
    assert _percentile([], 50) == 0.0


def test_percentile_single():
    assert _percentile([42.0], 50) == 42.0


# ── suggest_target_range ───────────────────────────────────────────────────────

def test_suggest_target_range_no_db():
    t = get_template("sleep_quality")
    result = suggest_target_range(t, None)
    assert result["has_data"] is False
    assert result["suggested_min"] == 72
    assert result["suggested_max"] == 100
    assert result["data_points"] == 0


def test_suggest_target_range_not_queryable():
    t = get_template("pace_improvement")
    result = suggest_target_range(t, MagicMock())
    assert result["has_data"] is False


def test_suggest_target_range_insufficient_data(test_db):
    from app.models.metric_reading import MetricReading, MetricSource, MetricType
    for i in range(5):
        r = MetricReading(
            id=1000 + i,
            timestamp=datetime.now(timezone.utc),
            metric_type=MetricType.sleep_score,
            value=80.0,
            source=MetricSource.garmin,
        )
        test_db.add(r)
    test_db.commit()

    t = get_template("sleep_quality")
    result = suggest_target_range(t, test_db)
    assert result["has_data"] is False  # < 7 data points


def test_suggest_target_range_higher_direction(test_db):
    from app.models.metric_reading import MetricReading, MetricSource, MetricType
    values = [74, 76, 78, 80, 82, 84, 86, 88, 90, 92]
    for i, v in enumerate(values):
        r = MetricReading(
            id=2000 + i,
            timestamp=datetime.now(timezone.utc),
            metric_type=MetricType.sleep_score,
            value=float(v),
            source=MetricSource.garmin,
        )
        test_db.add(r)
    test_db.commit()

    t = get_template("sleep_quality")
    result = suggest_target_range(t, test_db)
    assert result["has_data"] is True
    assert result["suggested_min"] is not None
    assert result["suggested_max"] == 100  # template default
    assert result["suggested_min"] >= 72   # at least the template default_min
    assert result["data_points"] == 10


def test_suggest_target_range_lower_direction(test_db):
    from app.models.metric_reading import MetricReading, MetricSource, MetricType
    values = [48, 50, 52, 54, 56, 58, 60, 62, 64, 66]
    for i, v in enumerate(values):
        r = MetricReading(
            id=3000 + i,
            timestamp=datetime.now(timezone.utc),
            metric_type=MetricType.resting_hr,
            value=float(v),
            source=MetricSource.garmin,
        )
        test_db.add(r)
    test_db.commit()

    t = get_template("resting_hr")
    result = suggest_target_range(t, test_db)
    assert result["has_data"] is True
    assert result["suggested_min"] == 44   # template default_min
    assert result["suggested_max"] is not None
    assert result["suggested_max"] <= 58   # at most the template default_max


def test_suggest_target_range_note_contains_data_points(test_db):
    from app.models.metric_reading import MetricReading, MetricSource, MetricType
    for i in range(10):
        r = MetricReading(
            id=4000 + i,
            timestamp=datetime.now(timezone.utc),
            metric_type=MetricType.hrv,
            value=55.0 + i,
            source=MetricSource.garmin,
        )
        test_db.add(r)
    test_db.commit()

    t = get_template("hrv")
    result = suggest_target_range(t, test_db)
    assert result["has_data"] is True
    assert "10" in result["note"]


# ── build_goal_from_template ──────────────────────────────────────────────────

def test_build_from_perpetual_template():
    t = get_template("sleep_quality")
    result = build_goal_from_template(t, {"title": "Maintain sleep quality"})
    assert result["goal_type"] == "perpetual"
    assert result["target_metric_type"] == "sleep_score"
    assert result["target_min"] == 72
    assert result["target_max"] == 100
    assert result["template_id"] == "sleep_quality"


def test_build_from_perpetual_overrides_range():
    t = get_template("sleep_quality")
    result = build_goal_from_template(t, {"title": "Sleep", "target_min": 75, "target_max": 95})
    assert result["target_min"] == 75
    assert result["target_max"] == 95


def test_build_from_achievement_template():
    t = get_template("race_half_marathon")
    result = build_goal_from_template(t, {
        "title": "Run sub-2 half marathon",
        "target_date": "2026-11-15",
    })
    assert result["goal_type"] == "achievement"
    assert result["target_date"] == "2026-11-15"
    assert result["template_id"] == "race_half_marathon"


def test_build_from_achievement_with_capability():
    t = get_template("race_half_marathon")
    result = build_goal_from_template(t, {
        "title": "Half marathon",
        "capability_data": {"long_run_km": "14", "weekly_volume_km": "45"},
    })
    assert result["description"] is not None
    assert "14" in result["description"]
    assert "45" in result["description"]


def test_build_from_habit_template():
    t = get_template("cooking_frequency")
    result = build_goal_from_template(t, {"title": "Cook at home 5x/week"})
    assert result["goal_type"] == "habit"
    assert result["habit_type"] == "count"
    assert result["habit_period"] == "week"
    assert result["weekly_target"] == 5
    assert isinstance(result["capture_keywords"], list)
    assert len(result["capture_keywords"]) > 0


def test_build_from_habit_uses_user_target():
    t = get_template("reading")
    result = build_goal_from_template(t, {"title": "Read", "weekly_target": 5})
    assert result["weekly_target"] == 5


def test_build_uses_suggested_title_when_no_user_title():
    t = get_template("cooking_frequency")
    result = build_goal_from_template(t, {})
    assert result["title"] == t["suggested_title"]


# ── capture keyword matching ──────────────────────────────────────────────────

def test_match_goal_by_keywords():
    import json
    from app.services.capture import match_goal_by_keywords
    from unittest.mock import MagicMock

    goal = MagicMock()
    goal.capture_keywords = json.dumps(["cooked", "made dinner"])
    goals = [goal]

    assert match_goal_by_keywords("I cooked pasta tonight", goals) is goal
    assert match_goal_by_keywords("made dinner for the family", goals) is goal
    assert match_goal_by_keywords("went for a run", goals) is None


def test_match_goal_by_keywords_word_boundary():
    import json
    from app.services.capture import match_goal_by_keywords
    from unittest.mock import MagicMock

    goal = MagicMock()
    goal.capture_keywords = json.dumps(["cook"])
    goals = [goal]

    # "cooking" should not match "cook" at word boundary
    assert match_goal_by_keywords("I was cooking tonight", goals) is None
    assert match_goal_by_keywords("I cook at home", goals) is goal


def test_match_goal_by_keywords_no_keywords():
    from app.services.capture import match_goal_by_keywords
    from unittest.mock import MagicMock

    goal = MagicMock()
    goal.capture_keywords = None
    goals = [goal]

    assert match_goal_by_keywords("I cooked pasta", goals) is None


def test_match_goal_by_keywords_empty_list():
    import json
    from app.services.capture import match_goal_by_keywords
    from unittest.mock import MagicMock

    goal = MagicMock()
    goal.capture_keywords = json.dumps([])
    goals = [goal]

    assert match_goal_by_keywords("anything here", goals) is None
