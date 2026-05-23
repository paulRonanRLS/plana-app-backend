"""Unit tests for app/bot/intent.py.

All tests run in stub mode (client=None) — no real Claude calls.
Claude integration is covered by live tests only.
"""

from app.bot.intent import INTENTS, _stub_classify, classify_intent


# ── _stub_classify ─────────────────────────────────────────────────────────────

def test_stub_morning_forces_checkin():
    assert _stub_classify("anything at all", is_morning=True) == "morning_checkin"


def test_stub_physical_state_sore():
    assert _stub_classify("my legs are sore", is_morning=False) == "physical_state"


def test_stub_physical_state_fatigue():
    assert _stub_classify("feeling fatigued today", is_morning=False) == "physical_state"


def test_stub_illness_sick():
    assert _stub_classify("I think I'm getting sick", is_morning=False) == "illness_log"


def test_stub_illness_recovering():
    assert _stub_classify("finally recovering from that cold", is_morning=False) == "illness_log"


def test_stub_goal_query():
    assert _stub_classify("how is my goal progress?", is_morning=False) == "goal_query"


def test_stub_goal_status():
    assert _stub_classify("what's my status", is_morning=False) == "goal_query"


def test_stub_metric_weight():
    assert _stub_classify("weight 74.5kg this morning", is_morning=False) == "metric_log"


def test_stub_metric_alcohol():
    assert _stub_classify("had 3 units last night", is_morning=False) == "metric_log"


def test_stub_progress_ran():
    assert _stub_classify("ran 10k this morning", is_morning=False) == "progress_capture"


def test_stub_progress_completed():
    assert _stub_classify("completed chapter 3 today", is_morning=False) == "progress_capture"


def test_stub_free_response_fallback():
    assert _stub_classify("hello there", is_morning=False) == "free_response"


def test_stub_free_response_generic():
    assert _stub_classify("that sounds good", is_morning=False) == "free_response"


# ── classify_intent ────────────────────────────────────────────────────────────

def test_classify_no_client_uses_stub():
    result = classify_intent("my knee aches", is_morning=False, client=None)
    assert result == "physical_state"


def test_classify_morning_no_client():
    result = classify_intent("good morning", is_morning=True, client=None)
    assert result == "morning_checkin"


def test_classify_returns_valid_intent(monkeypatch):
    """When Claude returns a valid label it is passed through unchanged."""
    from unittest.mock import MagicMock
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="goal_query")]
    result = classify_intent("how are my goals?", is_morning=False, client=client)
    assert result == "goal_query"


def test_classify_falls_back_on_unknown_label(monkeypatch):
    """When Claude returns an unrecognised label, stub fallback is used."""
    from unittest.mock import MagicMock
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="gibberish")]
    result = classify_intent("ran 5k today", is_morning=False, client=client)
    assert result in INTENTS


def test_classify_falls_back_on_api_error():
    from unittest.mock import MagicMock
    client = MagicMock()
    client.messages.create.side_effect = Exception("API timeout")
    result = classify_intent("anything", is_morning=False, client=client)
    assert result in INTENTS


# ── INTENTS constant ───────────────────────────────────────────────────────────

def test_all_intents_defined():
    expected = {
        "morning_checkin",
        "progress_capture",
        "physical_state",
        "illness_log",
        "metric_log",
        "goal_query",
        "activity_query",
        "free_response",
    }
    assert INTENTS == expected


# ── activity_query stub ────────────────────────────────────────────────────────

def test_stub_activity_query_ride_yesterday():
    assert _stub_classify("what was my ride yesterday?", is_morning=False) == "activity_query"


def test_stub_activity_query_run_last_week():
    assert _stub_classify("how far did I run last week", is_morning=False) == "activity_query"


def test_stub_activity_query_ride_sunday():
    assert _stub_classify("show me my ride on Sunday", is_morning=False) == "activity_query"


def test_stub_activity_query_workout_today():
    assert _stub_classify("what was my workout today?", is_morning=False) == "activity_query"


def test_stub_activity_no_temporal_not_activity_query():
    """An activity keyword without a temporal reference should not be activity_query."""
    result = _stub_classify("I love to run", is_morning=False)
    assert result != "activity_query"


def test_stub_activity_query_session_last():
    assert _stub_classify("what was my training session last Tuesday?", is_morning=False) == "activity_query"
