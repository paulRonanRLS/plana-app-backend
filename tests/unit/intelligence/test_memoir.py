"""Unit tests for app/intelligence/memoir.py."""

from unittest.mock import MagicMock

from app.intelligence.memoir import draft
from app.models.goal import Goal, GoalState
from app.models.milestone import Milestone, MilestoneState
from app.models.sacrifice import ResourceType, Sacrifice


def _goal(state: GoalState = GoalState.completed) -> Goal:
    g = Goal(title="Run a marathon", state=state)
    return g


def _milestone(title: str, state: MilestoneState) -> Milestone:
    return Milestone(title=title, state=state, goal_id=1)


def _sacrifice(resource: ResourceType) -> Sacrifice:
    return Sacrifice(resource=resource, goal_id=1)


# ── draft ──────────────────────────────────────────────────────────────────────

def test_draft_no_client_completed():
    result = draft(_goal(GoalState.completed), [], [], client=None)
    assert "completed" in result.lower()
    assert "Run a marathon" in result


def test_draft_no_client_released():
    result = draft(_goal(GoalState.released), [], [], client=None)
    assert "released" in result.lower()
    assert "Run a marathon" in result


def test_draft_calls_claude():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="I set out to run a marathon...")]
    result = draft(_goal(), [], [], client)
    assert result == "I set out to run a marathon..."
    client.messages.create.assert_called_once()


def test_draft_strips_whitespace():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="  memoir text  ")]
    assert draft(_goal(), [], [], client) == "memoir text"


def test_draft_falls_back_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("network error")
    result = draft(_goal(GoalState.released), [], [], client)
    assert "released" in result.lower()


def test_draft_prompt_includes_goal_title():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    draft(_goal(), [], [], client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Run a marathon" in prompt


def test_draft_prompt_includes_milestones():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    milestones = [
        _milestone("First 10k", MilestoneState.achieved),
        _milestone("Half marathon", MilestoneState.missed),
    ]
    draft(_goal(), [], milestones, client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "First 10k" in prompt
    assert "Half marathon" in prompt


def test_draft_prompt_includes_sacrifices():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    sacrifices = [
        _sacrifice(ResourceType.time),
        _sacrifice(ResourceType.time),
        _sacrifice(ResourceType.recovery),
    ]
    draft(_goal(), sacrifices, [], client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Sacrifices logged: 3" in prompt
    assert "time" in prompt


def test_draft_prompt_includes_release_reason():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="ok")]
    goal = _goal(GoalState.released)
    goal.release_reason = "Injury forced a reassessment"
    draft(goal, [], [], client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Injury forced a reassessment" in prompt
