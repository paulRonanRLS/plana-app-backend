"""Unit tests for app/intelligence/intent.py."""

from unittest.mock import MagicMock

from app.bot.intent import INTENTS
from app.intelligence.intent import classify
from app.models.goal import Goal, GoalState


def _goal(title: str, state: GoalState = GoalState.active) -> Goal:
    return Goal(title=title, state=state)


# ── classify ───────────────────────────────────────────────────────────────────

def test_morning_forces_checkin_with_full_confidence():
    result = classify("anything", [], is_morning=True, client=None)
    assert result == {"intent": "morning_checkin", "confidence": 1.0}


def test_morning_forces_checkin_even_with_client():
    client = MagicMock()
    result = classify("hello", [], is_morning=True, client=client)
    assert result["intent"] == "morning_checkin"
    assert result["confidence"] == 1.0
    client.messages.create.assert_not_called()


def test_no_client_uses_stub_with_half_confidence():
    result = classify("my legs are sore", [], is_morning=False, client=None)
    assert result["intent"] == "physical_state"
    assert result["confidence"] == 0.5


def test_no_client_fallback_is_valid_intent():
    result = classify("random words here", [], is_morning=False, client=None)
    assert result["intent"] in INTENTS


def test_with_client_passes_through_valid_label():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="goal_query")]
    result = classify("how are my goals?", [], is_morning=False, client=client)
    assert result == {"intent": "goal_query", "confidence": 0.9}


def test_with_client_falls_back_on_unknown_label():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="gibberish_label")]
    result = classify("ran 5k today", [], is_morning=False, client=client)
    assert result["intent"] in INTENTS
    assert result["confidence"] == 0.5


def test_with_client_falls_back_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API error")
    result = classify("anything", [], is_morning=False, client=client)
    assert result["intent"] in INTENTS
    assert result["confidence"] == 0.5


def test_prompt_includes_active_goals():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="free_response")]
    goals = [_goal("Marathon"), _goal("Novel")]
    classify("hello", goals, is_morning=False, client=client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Marathon" in prompt
    assert "Novel" in prompt


def test_prompt_excludes_terminal_goals():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="free_response")]
    goals = [
        _goal("Active", GoalState.active),
        _goal("Done", GoalState.completed),
        _goal("Old", GoalState.released),
    ]
    classify("hi", goals, is_morning=False, client=client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Active" in prompt
    assert "Done" not in prompt
    assert "Old" not in prompt


def test_returns_dict_with_intent_and_confidence():
    result = classify("hello", [], is_morning=False, client=None)
    assert "intent" in result
    assert "confidence" in result
    assert isinstance(result["confidence"], float)
