"""Unit tests for generate_milestones() in app/intelligence/milestones.py.

Separate file from test_milestones.py to avoid touching existing tests.
"""

import json
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.intelligence.milestones import generate_milestones
from app.models.goal import Goal, GoalState
from app.services.capability import CapabilityBaseline


# ── helpers ────────────────────────────────────────────────────────────────────

def _goal(title="Run a marathon", target_date=date(2026, 10, 1), description=None):
    return Goal(
        title=title,
        state=GoalState.active,
        description=description,
        target_date=target_date,
    )


def _run_baseline(**kwargs):
    defaults = dict(
        goal_type="run",
        long_run_km=14.5,
        weekly_volume_km=35.0,
        avg_pace_min_per_km=5.8,
        run_count=24,
    )
    defaults.update(kwargs)
    return CapabilityBaseline(**defaults)


def _ride_baseline(**kwargs):
    defaults = dict(
        goal_type="ride",
        ftp_estimate_w=240.0,
        longest_ride_km=110.0,
        weekly_tss=380.0,
        ride_count=18,
    )
    defaults.update(kwargs)
    return CapabilityBaseline(**defaults)


def _general_baseline():
    return CapabilityBaseline(goal_type="general")


# ── stub mode (client=None) ────────────────────────────────────────────────────

def test_stub_returns_three_milestones():
    result = generate_milestones(_goal(), _run_baseline(), client=None)
    assert len(result) == 3


def test_stub_milestones_have_required_keys():
    result = generate_milestones(_goal(), _run_baseline(), client=None)
    for m in result:
        assert "title" in m
        assert "description" in m
        assert "target_date" in m
        assert "sequence" in m


def test_stub_milestones_are_ordered():
    result = generate_milestones(_goal(), _run_baseline(), client=None)
    seqs = [m["sequence"] for m in result]
    assert seqs == [1, 2, 3]


def test_stub_dates_span_toward_target():
    today = date(2026, 5, 24)
    target = date(2026, 10, 1)
    result = generate_milestones(_goal(target_date=target), _run_baseline(), client=None, today=today)
    dates = [date.fromisoformat(m["target_date"]) for m in result if m["target_date"]]
    assert len(dates) == 3
    assert dates[0] < dates[1] < dates[2]
    assert dates[2] == target


def test_stub_last_milestone_is_target_date():
    today = date(2026, 5, 24)
    target = date(2026, 12, 31)
    result = generate_milestones(_goal(target_date=target), _run_baseline(), client=None, today=today)
    assert result[-1]["target_date"] == str(target)


def test_stub_no_target_date_uses_12_week_horizon():
    today = date(2026, 5, 24)
    result = generate_milestones(_goal(target_date=None), _run_baseline(), client=None, today=today)
    last_date = date.fromisoformat(result[-1]["target_date"])
    # Should be ~12 weeks out
    assert (last_date - today).days == 84


def test_stub_mentions_goal_title():
    result = generate_milestones(_goal("Finish the Ironman"), _run_baseline(), client=None)
    all_text = " ".join(m["description"] for m in result)
    assert "Finish the Ironman" in all_text


def test_stub_works_with_general_baseline():
    result = generate_milestones(_goal(), _general_baseline(), client=None)
    assert len(result) == 3


def test_stub_works_with_ride_baseline():
    result = generate_milestones(_goal("Century ride"), _ride_baseline(), client=None)
    assert len(result) == 3


# ── Claude-enabled mode ────────────────────────────────────────────────────────

def test_calls_claude_with_goal_title():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    generate_milestones(_goal("Sub-4 marathon"), _run_baseline(), client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "Sub-4 marathon" in prompt


def test_calls_claude_with_capability_context_run():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    generate_milestones(_goal(), _run_baseline(long_run_km=14.5, weekly_volume_km=35.0), client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "14.5" in prompt
    assert "35.0" in prompt


def test_calls_claude_with_capability_context_ride():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    generate_milestones(_goal("Century ride"), _ride_baseline(ftp_estimate_w=240.0), client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "240" in prompt


def test_no_capability_context_for_general_goal():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    generate_milestones(_goal("Write a novel"), _general_baseline(), client)
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    # Should not include running or cycling jargon
    assert "pace" not in prompt.lower()
    assert "ftp" not in prompt.lower()


def test_returns_parsed_claude_response():
    client = MagicMock()
    milestones = [
        {"title": "16k long run", "description": "Complete a 16km long run", "target_date": "2026-07-01", "sequence": 1},
        {"title": "20k long run", "description": "Complete a 20km long run", "target_date": "2026-08-15", "sequence": 2},
        {"title": "Race day", "description": "Run the marathon sub-4h", "target_date": "2026-10-01", "sequence": 3},
    ]
    client.messages.create.return_value.content = [MagicMock(text=json.dumps(milestones))]
    result = generate_milestones(_goal(), _run_baseline(), client)
    assert len(result) == 3
    assert result[0]["title"] == "16k long run"


def test_returns_empty_on_api_error():
    client = MagicMock()
    client.messages.create.side_effect = Exception("API down")
    result = generate_milestones(_goal(), _run_baseline(), client)
    assert result == []


def test_returns_empty_on_invalid_json():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="not json")]
    result = generate_milestones(_goal(), _run_baseline(), client)
    assert result == []


def test_returns_empty_on_non_list_response():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text='{"single": "object"}')]
    result = generate_milestones(_goal(), _run_baseline(), client)
    assert result == []


def test_filters_dicts_without_title():
    client = MagicMock()
    raw = [
        {"title": "Valid", "description": "ok", "target_date": None, "sequence": 1},
        {"description": "Missing title"},
        "not a dict",
    ]
    client.messages.create.return_value.content = [MagicMock(text=json.dumps(raw))]
    result = generate_milestones(_goal(), _run_baseline(), client)
    assert len(result) == 1
    assert result[0]["title"] == "Valid"


def test_includes_target_date_in_prompt():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="[]")]
    generate_milestones(_goal(target_date=date(2026, 10, 1)), _run_baseline(), client, today=date(2026, 5, 1))
    prompt = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "2026-10-01" in prompt
    assert "2026-05-01" in prompt
