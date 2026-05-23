"""Unit tests for app/intelligence/milestones.py."""

import json
from datetime import date
from unittest.mock import MagicMock

from app.intelligence.milestones import generate
from app.models.goal import Goal, GoalState


def _goal(title: str = "Run a marathon") -> Goal:
    return Goal(
        title=title,
        state=GoalState.active,
        description="Sub-4 hour finish",
        target_date=date(2026, 10, 1),
    )


# ── generate ───────────────────────────────────────────────────────────────────

def test_generate_no_client_returns_empty():
    assert generate(_goal(), client=None) == []


def test_generate_calls_claude():
    client = MagicMock()
    milestones = [
        {"title": "First 10k", "description": "Run 10k", "target_date": "2026-06-01"},
        {"title": "Half marathon", "description": "Run 21k", "target_date": "2026-08-01"},
    ]
    client.messages.create.return_value.content = [MagicMock(text=json.dumps(milestones))]
    result = generate(_goal(), client)
    assert len(result) == 2
    assert result[0]["title"] == "First 10k"


def test_generate_returns_only_dicts_with_title():
    client = MagicMock()
    raw = [
        {"title": "Valid", "description": "ok", "target_date": None},
        {"description": "No title"},
        "not a dict",
    ]
    client.messages.create.return_value.content = [MagicMock(text=json.dumps(raw))]
    result = generate(_goal(), client)
    assert len(result) == 1
    assert result[0]["title"] == "Valid"


def test_generate_returns_empty_on_non_list_response():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text='{"not": "a list"}')]
    assert generate(_goal(), client) == []


def test_generate_returns_empty_on_invalid_json():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="not json at all")]
    assert generate(_goal(), client) == []


def test_generate_returns_empty_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API failure")
    assert generate(_goal(), client) == []


def test_generate_prompt_includes_goal_title():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    generate(_goal("Finish the novel"), client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Finish the novel" in prompt


def test_generate_prompt_includes_target_date():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    goal = _goal()
    generate(goal, client, today=date(2026, 5, 1))
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "2026-10-01" in prompt
    assert "2026-05-01" in prompt


def test_generate_goal_without_target_date():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    goal = Goal(title="Open-ended goal", state=GoalState.active)
    generate(goal, client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "No fixed deadline" in prompt
