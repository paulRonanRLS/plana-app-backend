"""Unit tests for app/intelligence/checkin.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.intelligence.checkin import (
    build_response,
    build_system_prompt,
    _format_garmin_readings,
    _query_today_garmin,
)
from app.models.goal import Goal, GoalState
from app.models.metric_reading import MetricReading, MetricSource, MetricType

_reading_id = 0


def _add_garmin(db, metric_type: MetricType, value: float, timestamp=None) -> MetricReading:
    global _reading_id
    _reading_id += 1
    ts = timestamp or datetime.now(timezone.utc)
    r = MetricReading(
        id=_reading_id,
        timestamp=ts,
        metric_type=metric_type,
        value=value,
        source=MetricSource.garmin,
    )
    db.add(r)
    db.commit()
    return r


def _goal(title: str, state: GoalState, description: str | None = None) -> Goal:
    return Goal(title=title, state=state, description=description)


# ── build_system_prompt ────────────────────────────────────────────────────────

def test_prompt_contains_persona():
    assert "planA" in build_system_prompt([])


def test_prompt_no_goals():
    assert "No active goals" in build_system_prompt([])


def test_prompt_shows_active_goal():
    goals = [_goal("Run a marathon", GoalState.active)]
    assert "Run a marathon" in build_system_prompt(goals)


def test_prompt_shows_primacy_as_inviolable():
    goals = [_goal("Marathon", GoalState.primacy)]
    prompt = build_system_prompt(goals)
    assert "inviolable" in prompt
    assert "Marathon" in prompt


def test_prompt_excludes_completed_goals():
    goals = [
        _goal("Active", GoalState.active),
        _goal("Done", GoalState.completed),
    ]
    prompt = build_system_prompt(goals)
    assert "Active" in prompt
    assert "Done" not in prompt


def test_prompt_excludes_released_goals():
    goals = [_goal("Old", GoalState.released)]
    assert "Old" not in build_system_prompt(goals)


def test_prompt_includes_goal_description():
    goals = [_goal("Marathon", GoalState.active, description="Sub-4 hour finish")]
    assert "Sub-4 hour finish" in build_system_prompt(goals)


def test_prompt_includes_resource_data():
    prompt = build_system_prompt(
        [],
        time_envelope_hours=62.0,
        time_ratio=0.8,
        recovery_envelope_tss=320.0,
        recovery_ratio=0.9,
        attention_count=3,
    )
    assert "62" in prompt
    assert "320" in prompt
    assert "3 open items" in prompt


def test_prompt_omits_resource_section_when_no_data():
    prompt = build_system_prompt([])
    assert "resource state" not in prompt.lower()


def test_prompt_shows_all_active_states():
    goals = [
        _goal("P", GoalState.primacy),
        _goal("S", GoalState.subordinate),
        _goal("D", GoalState.drifting),
        _goal("A", GoalState.active),
    ]
    prompt = build_system_prompt(goals)
    assert "[primacy]" in prompt
    assert "[subordinate]" in prompt
    assert "[drifting]" in prompt
    assert "[active]" in prompt


# ── build_response ─────────────────────────────────────────────────────────────

def test_build_response_no_client_returns_stub():
    resp = build_response([], [], client=None)
    assert "morning" in resp.lower() or "feeling" in resp.lower()


def test_build_response_calls_claude_with_messages():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="How are you feeling?")]
    goals = [_goal("Marathon", GoalState.active)]
    messages = [{"role": "user", "content": "morning"}]

    result = build_response(messages, goals, client)

    assert result == "How are you feeling?"
    client.messages.create.assert_called_once()
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["messages"] == messages
    assert "Marathon" in call_kwargs["system"]


def test_build_response_strips_whitespace():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="  Response text.  ")]
    result = build_response([], [], client)
    assert result == "Response text."


def test_build_response_falls_back_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("network error")
    result = build_response([], [], client)
    assert "morning" in result.lower() or "feeling" in result.lower()


def test_build_response_trims_to_20_messages():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    messages = [{"role": "user", "content": str(i)} for i in range(30)]
    build_response(messages, [], client)
    sent = client.messages.create.call_args.kwargs["messages"]
    assert len(sent) == 20
    assert sent[0]["content"] == "10"


def test_build_response_passes_resource_data_to_prompt():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    build_response(
        [], [],
        client,
        time_envelope_hours=62.0,
        time_ratio=1.1,
    )
    system = client.messages.create.call_args.kwargs["system"]
    assert "62" in system


# ── Garmin readings in system prompt ──────────────────────────────────────────

def test_prompt_includes_garmin_sleep_score():
    prompt = build_system_prompt([], garmin_readings={"sleep_score": 78.0})
    assert "78" in prompt
    assert "Sleep score" in prompt


def test_prompt_includes_garmin_hrv():
    prompt = build_system_prompt([], garmin_readings={"hrv": 65.0})
    assert "65" in prompt
    assert "HRV" in prompt


def test_prompt_includes_garmin_sleep_duration():
    prompt = build_system_prompt([], garmin_readings={"sleep_duration_hours": 7.5})
    assert "7.5" in prompt
    assert "Sleep duration" in prompt


def test_prompt_includes_garmin_resting_hr():
    prompt = build_system_prompt([], garmin_readings={"resting_hr": 52.0})
    assert "52" in prompt
    assert "Resting HR" in prompt


def test_prompt_includes_garmin_body_battery():
    prompt = build_system_prompt([], garmin_readings={"body_battery": 72.0})
    assert "72" in prompt
    assert "Body battery" in prompt


def test_prompt_includes_garmin_stress():
    prompt = build_system_prompt([], garmin_readings={"stress": 28.0})
    assert "28" in prompt
    assert "Stress" in prompt


def test_prompt_garmin_section_has_provenance_label():
    prompt = build_system_prompt([], garmin_readings={"sleep_score": 78.0})
    assert "database" in prompt


def test_prompt_omits_garmin_section_when_no_readings():
    prompt = build_system_prompt([], garmin_readings={})
    assert "Garmin" not in prompt
    assert "Sleep score" not in prompt


def test_prompt_omits_garmin_section_when_none():
    prompt = build_system_prompt([])
    assert "Sleep score" not in prompt


def test_prompt_omits_partial_missing_metrics():
    # Only what's present is shown
    prompt = build_system_prompt([], garmin_readings={"hrv": 65.0})
    assert "Sleep score" not in prompt
    assert "HRV" in prompt


def test_format_garmin_readings_all_metrics():
    readings = {
        "sleep_score": 78.0,
        "sleep_duration_hours": 7.5,
        "hrv": 65.0,
        "resting_hr": 52.0,
        "body_battery": 72.0,
        "stress": 28.0,
    }
    lines = _format_garmin_readings(readings)
    assert any("78" in l for l in lines)
    assert any("7.5" in l for l in lines)
    assert any("65" in l for l in lines)
    assert len(lines) == 6


def test_format_garmin_readings_empty():
    assert _format_garmin_readings({}) == []


def test_format_garmin_readings_skips_none():
    lines = _format_garmin_readings({"sleep_score": 78.0, "hrv": None})
    assert len(lines) == 1
    assert "78" in lines[0]


def test_format_garmin_sleep_duration_one_decimal():
    lines = _format_garmin_readings({"sleep_duration_hours": 7.5})
    assert "7.5h" in lines[0]


def test_format_garmin_hrv_unit():
    lines = _format_garmin_readings({"hrv": 65.0})
    assert "ms" in lines[0]


def test_format_garmin_resting_hr_unit():
    lines = _format_garmin_readings({"resting_hr": 52.0})
    assert "bpm" in lines[0]


# ── _query_today_garmin ────────────────────────────────────────────────────────

def test_query_today_garmin_no_db():
    assert _query_today_garmin(None) == {}


def test_query_today_garmin_returns_readings(test_db):
    _add_garmin(test_db, MetricType.sleep_score, 78.0)
    _add_garmin(test_db, MetricType.hrv, 65.0)
    _add_garmin(test_db, MetricType.resting_hr, 52.0)

    readings = _query_today_garmin(test_db)
    assert readings["sleep_score"] == 78.0
    assert readings["hrv"] == 65.0
    assert readings["resting_hr"] == 52.0


def test_query_today_garmin_excludes_non_garmin(test_db):
    global _reading_id
    _reading_id += 1
    r = MetricReading(
        id=_reading_id,
        timestamp=datetime.now(timezone.utc),
        metric_type=MetricType.sleep_score,
        value=70.0,
        source=MetricSource.manual,
    )
    test_db.add(r)
    test_db.commit()

    readings = _query_today_garmin(test_db)
    assert "sleep_score" not in readings


def test_query_today_garmin_excludes_old_readings(test_db):
    from datetime import timedelta
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    _add_garmin(test_db, MetricType.hrv, 60.0, timestamp=yesterday)

    readings = _query_today_garmin(test_db)
    assert "hrv" not in readings


def test_query_today_garmin_excludes_null_values(test_db):
    global _reading_id
    _reading_id += 1
    r = MetricReading(
        id=_reading_id,
        timestamp=datetime.now(timezone.utc),
        metric_type=MetricType.sleep_score,
        value=None,
        source=MetricSource.garmin,
    )
    test_db.add(r)
    test_db.commit()

    readings = _query_today_garmin(test_db)
    assert "sleep_score" not in readings


def test_query_today_garmin_excludes_activity_type(test_db):
    _add_garmin(test_db, MetricType.activity, 10.0)

    readings = _query_today_garmin(test_db)
    assert "activity" not in readings


# ── build_response with db ─────────────────────────────────────────────────────

def test_build_response_injects_garmin_readings_into_system(test_db):
    _add_garmin(test_db, MetricType.sleep_score, 78.0)

    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="How are you feeling?")]

    build_response([], [], client, db=test_db)

    system = client.messages.create.call_args.kwargs["system"]
    assert "78" in system
    assert "Sleep score" in system


def test_build_response_no_garmin_data_omits_section(test_db):
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]

    build_response([], [], client, db=test_db)

    system = client.messages.create.call_args.kwargs["system"]
    assert "Sleep score" not in system


def test_build_response_db_none_no_garmin_section():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]

    build_response([], [], client, db=None)

    system = client.messages.create.call_args.kwargs["system"]
    assert "Sleep score" not in system
