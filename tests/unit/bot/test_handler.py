"""Unit tests for pure functions in app/bot/handler.py.

handle_message itself is tested end-to-end in live tests.
Here we cover the deterministic helpers that can run without Telegram or Claude.
"""

from unittest.mock import MagicMock, patch

from app.bot.handler import (
    _CAPTURE_INTENTS,
    _build_system_prompt,
    _is_affirmative,
    _is_negative,
    _stub_response,
    _write_capture,
)
from app.models.goal import Goal, GoalState


# ── helpers ────────────────────────────────────────────────────────────────────

def _goal(title: str, state: GoalState, description: str | None = None) -> Goal:
    g = Goal(title=title, state=state, description=description)
    return g


# ── _build_system_prompt ───────────────────────────────────────────────────────

def test_prompt_contains_persona():
    prompt = _build_system_prompt([])
    assert "planA" in prompt


def test_prompt_no_goals():
    prompt = _build_system_prompt([])
    assert "No active goals" in prompt


def test_prompt_includes_active_goal():
    goals = [_goal("Run a marathon", GoalState.active)]
    prompt = _build_system_prompt(goals)
    assert "Run a marathon" in prompt


def test_prompt_highlights_primacy():
    goals = [
        _goal("Marathon", GoalState.primacy),
        _goal("Novel", GoalState.active),
    ]
    prompt = _build_system_prompt(goals)
    assert "inviolable" in prompt
    assert "Marathon" in prompt
    assert "Novel" in prompt


def test_prompt_excludes_completed_goals():
    goals = [
        _goal("Active", GoalState.active),
        _goal("Done", GoalState.completed),
    ]
    prompt = _build_system_prompt(goals)
    assert "Active" in prompt
    assert "Done" not in prompt


def test_prompt_excludes_released_goals():
    goals = [
        _goal("Ongoing", GoalState.subordinate),
        _goal("Old", GoalState.released),
    ]
    prompt = _build_system_prompt(goals)
    assert "Ongoing" in prompt
    assert "Old" not in prompt


def test_prompt_shows_all_active_states():
    goals = [
        _goal("Primacy goal", GoalState.primacy),
        _goal("Sub goal", GoalState.subordinate),
        _goal("Drifting goal", GoalState.drifting),
        _goal("Active goal", GoalState.active),
    ]
    prompt = _build_system_prompt(goals)
    assert "[primacy]" in prompt
    assert "[subordinate]" in prompt
    assert "[drifting]" in prompt
    assert "[active]" in prompt


def test_prompt_no_primacy_no_primacy_section():
    goals = [_goal("Plain goal", GoalState.active)]
    prompt = _build_system_prompt(goals)
    assert "inviolable" not in prompt


# ── _stub_response ─────────────────────────────────────────────────────────────

def test_stub_morning_response():
    resp = _stub_response("morning_checkin", is_morning=True)
    assert "morning" in resp.lower() or "feeling" in resp.lower()


def test_stub_morning_flag_overrides_intent():
    resp = _stub_response("free_response", is_morning=True)
    assert "morning" in resp.lower() or "feeling" in resp.lower()


def test_stub_progress_response():
    resp = _stub_response("progress_capture", is_morning=False)
    assert len(resp) > 0


def test_stub_physical_state_response():
    resp = _stub_response("physical_state", is_morning=False)
    assert len(resp) > 0


def test_stub_illness_response():
    resp = _stub_response("illness_log", is_morning=False)
    assert len(resp) > 0


def test_stub_metric_response():
    resp = _stub_response("metric_log", is_morning=False)
    assert len(resp) > 0


def test_stub_goal_query_response():
    resp = _stub_response("goal_query", is_morning=False)
    assert len(resp) > 0


def test_stub_free_response():
    resp = _stub_response("free_response", is_morning=False)
    assert len(resp) > 0


def test_stub_unknown_intent_returns_something():
    resp = _stub_response("nonexistent_intent", is_morning=False)
    assert len(resp) > 0


# ── _CAPTURE_INTENTS ───────────────────────────────────────────────────────────

def test_capture_intents_excludes_progress_capture():
    # progress_capture is handled via goal-matching flow, not the generic write path
    assert "progress_capture" not in _CAPTURE_INTENTS


def test_capture_intents_includes_physical_state():
    assert "physical_state" in _CAPTURE_INTENTS


def test_capture_intents_includes_illness_log():
    assert "illness_log" in _CAPTURE_INTENTS


def test_capture_intents_includes_metric_log():
    assert "metric_log" in _CAPTURE_INTENTS


def test_capture_intents_excludes_new_intents():
    # new intents have their own routing with direct DB writes
    for intent in ("sacrifice_log", "milestone_complete", "goal_state_change"):
        assert intent not in _CAPTURE_INTENTS


# ── _write_capture (Fix 1 behaviour) ──────────────────────────────────────────

def test_write_capture_physical_state_calls_record():
    with patch("app.bot.handler.capture_service") as mock_cs:
        _write_capture(MagicMock(), "physical_state", "sore calves")
        mock_cs.record_physical_state.assert_called_once()


def test_write_capture_illness_log_calls_record():
    with patch("app.bot.handler.capture_service") as mock_cs:
        _write_capture(MagicMock(), "illness_log", "I think I'm getting sick")
        mock_cs.record_illness.assert_called_once()


def test_write_capture_metric_log_calls_record():
    with patch("app.bot.handler.capture_service") as mock_cs:
        _write_capture(MagicMock(), "metric_log", "74.5kg this morning")
        mock_cs.record_metric.assert_called_once()


def test_write_capture_morning_checkin_is_noop():
    # morning_checkin override must not write anything — only original_intent does
    with patch("app.bot.handler.capture_service") as mock_cs:
        _write_capture(MagicMock(), "morning_checkin", "my HRV is 45")
        mock_cs.record_physical_state.assert_not_called()
        mock_cs.record_illness.assert_not_called()
        mock_cs.record_metric.assert_not_called()


def test_write_capture_sacrifice_log_is_noop():
    with patch("app.bot.handler.capture_service") as mock_cs:
        _write_capture(MagicMock(), "sacrifice_log", "sacrificed my run")
        mock_cs.record_physical_state.assert_not_called()
        mock_cs.record_illness.assert_not_called()
        mock_cs.record_metric.assert_not_called()


# ── _is_affirmative / _is_negative (Fix 2 helpers) ────────────────────────────

def test_is_affirmative_yes():
    assert _is_affirmative("yes")


def test_is_affirmative_review():
    assert _is_affirmative("review it")


def test_is_affirmative_yeah():
    assert _is_affirmative("yeah please")


def test_is_affirmative_false_for_no():
    assert not _is_affirmative("no not now")


def test_is_negative_no():
    assert _is_negative("no")


def test_is_negative_not_now():
    assert _is_negative("not now")


def test_is_negative_dismiss():
    assert _is_negative("dismiss")


def test_is_negative_false_for_yes():
    assert not _is_negative("yes review it")


# ── _stub_response for new intents ─────────────────────────────────────────────

def test_stub_sacrifice_log_response():
    resp = _stub_response("sacrifice_log", is_morning=False)
    assert len(resp) > 0


def test_stub_milestone_complete_response():
    resp = _stub_response("milestone_complete", is_morning=False)
    assert len(resp) > 0


def test_stub_goal_state_change_response():
    resp = _stub_response("goal_state_change", is_morning=False)
    assert len(resp) > 0
