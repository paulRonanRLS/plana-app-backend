"""Unit tests for app/intelligence/checkin.py."""

from unittest.mock import MagicMock

from app.intelligence.checkin import build_response, build_system_prompt
from app.models.goal import Goal, GoalState


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
