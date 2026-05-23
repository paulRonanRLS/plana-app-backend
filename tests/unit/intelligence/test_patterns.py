"""Unit tests for app/intelligence/patterns.py."""

from unittest.mock import MagicMock

from app.intelligence.patterns import synthesize, synthesize_stub
from app.models.goal import Goal, GoalState
from app.services.resource import WillpowerPattern


def _pattern(
    count: int = 5,
    dominant: str | None = "time",
    by_resource: dict | None = None,
) -> WillpowerPattern:
    if by_resource is None:
        by_resource = {"time": 3, "recovery": 1, "attention": 1, "willpower": 0}
    return WillpowerPattern(
        sacrifice_count_28d=count,
        dominant_resource=dominant,
        by_resource=by_resource,
    )


def _goal(title: str, state: GoalState = GoalState.active) -> Goal:
    return Goal(title=title, state=state)


# ── synthesize_stub ────────────────────────────────────────────────────────────

def test_stub_no_sacrifices():
    p = _pattern(count=0, dominant=None, by_resource={})
    assert "No sacrifices" in synthesize_stub(p)


def test_stub_includes_count():
    result = synthesize_stub(_pattern(count=7))
    assert "7" in result


def test_stub_includes_dominant_resource():
    result = synthesize_stub(_pattern(dominant="recovery"))
    assert "recovery" in result.lower() or "Recovery" in result


def test_stub_returns_string():
    assert isinstance(synthesize_stub(_pattern()), str)


# ── synthesize ─────────────────────────────────────────────────────────────────

def test_synthesize_no_client_uses_stub():
    result = synthesize(_pattern(), [], client=None)
    assert isinstance(result, str)
    assert len(result) > 0


def test_synthesize_calls_claude():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="Time is your binding constraint.")]
    result = synthesize(_pattern(), [], client)
    assert result == "Time is your binding constraint."
    client.messages.create.assert_called_once()


def test_synthesize_strips_whitespace():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="  pattern text  ")]
    assert synthesize(_pattern(), [], client) == "pattern text"


def test_synthesize_falls_back_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("timeout")
    result = synthesize(_pattern(count=3), [], client)
    assert "3" in result


def test_synthesize_prompt_includes_dominant_resource():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    synthesize(_pattern(dominant="willpower"), [], client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "willpower" in prompt


def test_synthesize_prompt_includes_goals():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    goals = [_goal("Marathon"), _goal("Novel")]
    synthesize(_pattern(), goals, client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Marathon" in prompt
    assert "Novel" in prompt


def test_synthesize_prompt_includes_counts():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    synthesize(_pattern(count=12), [], client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "12" in prompt
