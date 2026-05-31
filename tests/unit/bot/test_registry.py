"""Unit tests for app/bot/handlers/ — registry and handler contracts."""

import asyncio

from app.bot.handlers import REGISTRY
from app.bot.handlers.base import HandlerContext, IntentHandler

_EXPECTED_INTENTS = frozenset({
    "morning_checkin",
    "progress_capture",
    "physical_state",
    "illness_log",
    "metric_log",
    "goal_query",
    "activity_query",
    "sacrifice_log",
    "milestone_complete",
    "goal_state_change",
    "free_response",
})


# ── registry contents ──────────────────────────────────────────────────────────

def test_registry_has_all_eleven_intents():
    assert REGISTRY.all_intents() == _EXPECTED_INTENTS


def test_registry_all_intents_returns_frozenset():
    assert isinstance(REGISTRY.all_intents(), frozenset)


def test_registry_get_returns_handler_for_each_intent():
    for intent in _EXPECTED_INTENTS:
        handler = REGISTRY.get(intent)
        assert handler is not None, f"No handler registered for intent: {intent}"


def test_registry_get_unknown_intent_returns_none():
    assert REGISTRY.get("nonexistent_intent") is None


# ── handler contracts ──────────────────────────────────────────────────────────

def test_all_handlers_have_correct_intent_attribute():
    for intent in _EXPECTED_INTENTS:
        handler = REGISTRY.get(intent)
        assert handler.intent == intent, f"{type(handler).__name__}.intent should be '{intent}'"


def test_all_handlers_have_async_handle_method():
    for intent in _EXPECTED_INTENTS:
        handler = REGISTRY.get(intent)
        assert hasattr(handler, "handle"), f"{intent} handler missing handle()"
        assert asyncio.iscoroutinefunction(handler.handle), f"{intent}.handle() is not async"


def test_all_handlers_writes_to_db_returns_bool():
    for intent in _EXPECTED_INTENTS:
        handler = REGISTRY.get(intent)
        result = handler.writes_to_db()
        assert isinstance(result, bool), f"{intent}.writes_to_db() should return bool"


def test_all_handlers_uses_pending_capture_returns_bool():
    for intent in _EXPECTED_INTENTS:
        handler = REGISTRY.get(intent)
        result = handler.uses_pending_capture()
        assert isinstance(result, bool), f"{intent}.uses_pending_capture() should return bool"


def test_all_handlers_are_intent_handler_subclasses():
    for intent in _EXPECTED_INTENTS:
        handler = REGISTRY.get(intent)
        assert isinstance(handler, IntentHandler), (
            f"{type(handler).__name__} should subclass IntentHandler"
        )


# ── pending capture routing ────────────────────────────────────────────────────

def test_free_response_uses_pending_capture():
    assert REGISTRY.get("free_response").uses_pending_capture() is True


def test_all_other_handlers_do_not_use_pending_capture():
    for intent in _EXPECTED_INTENTS - {"free_response"}:
        handler = REGISTRY.get(intent)
        assert handler.uses_pending_capture() is False, (
            f"{intent} should not use pending capture"
        )


# ── HandlerContext ─────────────────────────────────────────────────────────────

def test_handler_context_instantiation():
    ctx = HandlerContext(
        text="test",
        intent="free_response",
        original_intent="free_response",
        is_morning=False,
        goals=[],
        db=None,
        claude_client=None,
        redis_client=None,
        pending_capture=None,
        pending_alert=None,
    )
    assert ctx.text == "test"
    assert ctx.confidence == 0.7
    assert ctx.messages == []


def test_handler_context_active_goals_filters_terminal(test_db):
    from datetime import datetime, timezone
    from app.models.goal import Goal, GoalState

    now = datetime.now(timezone.utc)
    active = Goal(title="Active", state=GoalState.active, created_at=now, updated_at=now)
    done = Goal(title="Done", state=GoalState.completed, created_at=now, updated_at=now)
    test_db.add_all([active, done])
    test_db.commit()
    test_db.refresh(active)
    test_db.refresh(done)

    goals = [active, done]
    ctx = HandlerContext(
        text="", intent="free_response", original_intent="free_response",
        is_morning=False, goals=goals, db=test_db, claude_client=None,
        redis_client=None, pending_capture=None, pending_alert=None,
    )
    assert len(ctx.active_goals) == 1
    assert ctx.active_goals[0].title == "Active"


# ── INTENTS consistency ────────────────────────────────────────────────────────

def test_registry_intents_match_intent_module():
    """INTENTS in intent.py must equal the registered handler set."""
    from app.bot.intent import INTENTS
    assert INTENTS == REGISTRY.all_intents()
