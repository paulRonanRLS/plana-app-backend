"""Unit tests for pure functions in app/bot/handler.py.

handle_message itself is tested end-to-end in live tests.
Here we cover the deterministic helpers that can run without Telegram or Claude.
"""

from app.bot.handler import _build_system_prompt, _stub_response
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
