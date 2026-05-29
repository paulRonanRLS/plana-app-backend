"""Unit tests for app/bot/outreach.py.

Verifies message content rules:
  - Drift alert surfaces the metric deviation and asks one question
  - Fade alert surfaces the absence and asks one question
  - Neither message recommends an action or suggests dropping the goal
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from unittest.mock import patch

from app.bot.outreach import send_drift_alert, send_fade_alert, _format_range
from app.services.drift import DriftEvent
from app.services.fade import FadeEvent


# ── helpers ────────────────────────────────────────────────────────────────────

def make_goal(title="Run a marathon", goal_id=1):
    goal = MagicMock()
    goal.id = goal_id
    goal.title = title
    return goal


def make_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── _format_range ──────────────────────────────────────────────────────────────

def test_format_range_both_bounds():
    assert _format_range(70.0, 75.0) == "70.0–75.0"


def test_format_range_min_only():
    assert "55.0" in _format_range(55.0, None)
    assert "≥" in _format_range(55.0, None)


def test_format_range_max_only():
    assert "80.0" in _format_range(None, 80.0)
    assert "≤" in _format_range(None, 80.0)


def test_format_range_no_bounds():
    assert _format_range(None, None) == "unknown"


# ── send_drift_alert ───────────────────────────────────────────────────────────

def test_drift_alert_sent_to_correct_chat(test_db):
    bot = make_bot()
    goal = make_goal("Weight control")
    event = DriftEvent(
        goal_id=1,
        goal_title="Weight control",
        metric_type="weight",
        days_outside_range=4,
        current_value=79.2,
        target_min=70.0,
        target_max=75.0,
    )
    run(send_drift_alert(bot, chat_id=12345, goal=goal, drift_event=event))
    bot.send_message.assert_called_once()
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 12345


def test_drift_alert_names_the_goal(test_db):
    bot = make_bot()
    goal = make_goal("Weight control")
    event = DriftEvent(1, "Weight control", "weight", 3, 79.2, 70.0, 75.0)
    run(send_drift_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "Weight control" in text


def test_drift_alert_shows_days_outside(test_db):
    bot = make_bot()
    goal = make_goal()
    event = DriftEvent(1, "Goal", "weight", 5, 80.0, 70.0, 75.0)
    run(send_drift_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "5" in text


def test_drift_alert_shows_current_value(test_db):
    bot = make_bot()
    goal = make_goal()
    event = DriftEvent(1, "Goal", "weight", 3, 79.5, 70.0, 75.0)
    run(send_drift_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "79.5" in text


def test_drift_alert_asks_question_not_recommendation(test_db):
    """Must end with a question, must not tell the user what to do."""
    bot = make_bot()
    goal = make_goal()
    event = DriftEvent(1, "Goal", "weight", 3, 79.5, 70.0, 75.0)
    run(send_drift_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "?" in text
    forbidden = ["you should", "you need to", "drop", "pause", "recommend", "suggest"]
    for phrase in forbidden:
        assert phrase.lower() not in text.lower(), f"Alert contains recommendation: '{phrase}'"


def test_drift_alert_handles_none_current_value(test_db):
    bot = make_bot()
    goal = make_goal()
    event = DriftEvent(1, "Goal", "weight", 3, None, 70.0, 75.0)
    run(send_drift_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "no recent reading" in text


# ── send_fade_alert ────────────────────────────────────────────────────────────

def test_fade_alert_sent_to_correct_chat(test_db):
    bot = make_bot()
    goal = make_goal("Write the novel")
    event = FadeEvent(1, "Write the novel", 18, None)
    run(send_fade_alert(bot, chat_id=99999, goal=goal, fade_event=event))
    kwargs = bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == 99999


def test_fade_alert_names_the_goal(test_db):
    bot = make_bot()
    goal = make_goal("Write the novel")
    event = FadeEvent(1, "Write the novel", 18, None)
    run(send_fade_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "Write the novel" in text


def test_fade_alert_shows_days_since_activity(test_db):
    bot = make_bot()
    goal = make_goal()
    event = FadeEvent(1, "Goal", 21, None)
    run(send_fade_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "21" in text


def test_fade_alert_asks_question_not_recommendation(test_db):
    """Must ask a question, must not tell the user what to do."""
    bot = make_bot()
    goal = make_goal()
    event = FadeEvent(1, "Goal", 18, None)
    run(send_fade_alert(bot, 1, goal, event))
    text = bot.send_message.call_args.kwargs["text"]
    assert "?" in text
    forbidden = ["you should", "you need to", "drop", "pause", "recommend", "suggest"]
    for phrase in forbidden:
        assert phrase.lower() not in text.lower(), f"Alert contains recommendation: '{phrase}'"


# ── pending alert storage ──────────────────────────────────────────────────────

def test_drift_alert_stores_pending_alert_when_redis_provided(test_db):
    from unittest.mock import MagicMock
    from app.bot import session as session_mgr

    bot = make_bot()
    goal = make_goal("Weight control", goal_id=5)
    event = DriftEvent(5, "Weight control", "weight", 3, 79.0, 70.0, 75.0)
    redis_client = MagicMock()

    with patch.object(session_mgr, "set_pending_alert") as mock_set:
        run(send_drift_alert(bot, 1, goal, event, redis_client=redis_client))
        mock_set.assert_called_once_with(redis_client, {"goal_id": 5, "alert_type": "drift"})


def test_drift_alert_no_pending_alert_without_redis(test_db):
    from app.bot import session as session_mgr

    bot = make_bot()
    goal = make_goal()
    event = DriftEvent(1, "Goal", "weight", 3, 79.0, 70.0, 75.0)

    with patch.object(session_mgr, "set_pending_alert") as mock_set:
        run(send_drift_alert(bot, 1, goal, event))  # no redis_client
        mock_set.assert_not_called()


def test_fade_alert_stores_pending_alert_when_redis_provided(test_db):
    from unittest.mock import MagicMock
    from app.bot import session as session_mgr

    bot = make_bot()
    goal = make_goal("Write the novel", goal_id=9)
    event = FadeEvent(9, "Write the novel", 18, None)
    redis_client = MagicMock()

    with patch.object(session_mgr, "set_pending_alert") as mock_set:
        run(send_fade_alert(bot, 1, goal, event, redis_client=redis_client))
        mock_set.assert_called_once_with(redis_client, {"goal_id": 9, "alert_type": "fade"})


def test_fade_alert_no_pending_alert_without_redis(test_db):
    from app.bot import session as session_mgr

    bot = make_bot()
    goal = make_goal()
    event = FadeEvent(1, "Goal", 18, None)

    with patch.object(session_mgr, "set_pending_alert") as mock_set:
        run(send_fade_alert(bot, 1, goal, event))  # no redis_client
        mock_set.assert_not_called()
