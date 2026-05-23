"""Unit tests for app/intelligence/activity_query.py."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.intelligence.activity_query import (
    _format_context,
    _format_stub,
    build_response,
)


def _activity(
    name="Morning Run",
    sport_type="Run",
    distance_m=10200,
    moving_time_s=3180,
    tss=None,
    ts=None,
):
    return {
        "timestamp": ts or datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc),
        "source": "strava",
        "name": name,
        "sport_type": sport_type,
        "distance_m": distance_m,
        "moving_time_s": moving_time_s,
        "elapsed_time_s": moving_time_s,
        "tss": tss,
    }


# ── _format_stub ───────────────────────────────────────────────────────────────

def test_format_stub_empty():
    assert _format_stub([]) == "No activities found for that period."


def test_format_stub_single_run():
    result = _format_stub([_activity()])
    assert "Morning Run" in result
    assert "km" in result
    assert "m" in result  # time includes minutes


def test_format_stub_includes_distance():
    result = _format_stub([_activity(distance_m=10200)])
    assert "10.2 km" in result


def test_format_stub_includes_duration():
    result = _format_stub([_activity(moving_time_s=3180)])
    # 3180s = 53m 0s
    assert "53m" in result


def test_format_stub_includes_tss_when_present():
    result = _format_stub([_activity(tss=85.0)])
    assert "TSS" in result
    assert "85" in result


def test_format_stub_omits_tss_when_none():
    result = _format_stub([_activity(tss=None)])
    assert "TSS" not in result


def test_format_stub_multiple_activities():
    activities = [_activity(name="Run A"), _activity(name="Ride B", sport_type="Ride")]
    result = _format_stub(activities)
    assert "Run A" in result
    assert "Ride B" in result


def test_format_stub_long_duration_shows_hours():
    result = _format_stub([_activity(moving_time_s=7200)])  # 2 hours
    assert "2h" in result


# ── _format_context ────────────────────────────────────────────────────────────

def test_format_context_empty():
    result = _format_context([])
    assert "No activities" in result


def test_format_context_includes_name():
    result = _format_context([_activity()])
    assert "Morning Run" in result


def test_format_context_includes_sport_type():
    result = _format_context([_activity(sport_type="Run")])
    assert "Run" in result


def test_format_context_includes_distance():
    result = _format_context([_activity(distance_m=10200)])
    assert "10.20 km" in result


def test_format_context_includes_date():
    result = _format_context([_activity(ts=datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc))])
    assert "Fri" in result or "22" in result


def test_format_context_shows_count():
    activities = [_activity(), _activity(name="Ride")]
    result = _format_context(activities)
    assert "2 activities" in result


# ── build_response ─────────────────────────────────────────────────────────────

def test_build_response_no_client_uses_stub():
    result = build_response("what was my run yesterday?", [], client=None)
    assert result == "No activities found for that period."


def test_build_response_no_client_formats_activity():
    result = build_response("what was my run?", [_activity()], client=None)
    assert "Morning Run" in result


def test_build_response_claude_called_with_context():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="You ran 10.2 km in 53 minutes.")]
    result = build_response("what was my run yesterday?", [_activity()], client=client)
    assert result == "You ran 10.2 km in 53 minutes."
    client.messages.create.assert_called_once()


def test_build_response_claude_error_falls_back_to_stub():
    client = MagicMock()
    client.messages.create.side_effect = Exception("timeout")
    result = build_response("what was my run?", [_activity()], client=client)
    assert "Morning Run" in result


def test_build_response_claude_empty_activities():
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="No activities found.")]
    result = build_response("any rides last week?", [], client=client)
    assert result == "No activities found."
