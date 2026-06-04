"""Telegram message handler — thin dispatcher over the intent handler registry.

Flow per message:
  1. Detect morning window (before 10am local time)
  2. Classify intent + confidence (Claude JSON response or keyword stub)
  3. Save original_intent; apply morning_checkin override if before 10am
  4. Append user message to Redis session
  5. Open DB; load all goals
  6. Check pending_alert (drift/fade acknowledgement) — yes/no short-circuits routing
  7. Dispatch to registered handler via REGISTRY; handler owns all routing logic
  8. Append assistant response to session
  9. Reply to user
"""

import asyncio
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot import session as session_mgr
from app.bot.handlers import REGISTRY
from app.bot.handlers.base import HandlerContext
from app.bot.intent import classify_intent_with_confidence
from app.core.claude_client import get_client
from app.core.redis_client import get_redis
from app.database import SessionLocal
from app.intelligence import goal_query as goal_query_module
from app.models.goal import Goal, GoalState
from app.services import capture as capture_service
from app.services.goal import TERMINAL_STATES

logger = logging.getLogger(__name__)

MORNING_CUTOFF_HOUR = 10
MAX_HISTORY = 20

# Kept for backward compatibility — tests import these from this module.
_CAPTURE_INTENTS = frozenset({"physical_state", "illness_log", "metric_log"})
_YES_WORDS = frozenset({"yes", "review", "yeah", "yep", "please", "sure", "ok", "okay"})
_NO_WORDS = frozenset({"no", "not now", "dismiss", "nope", "skip", "later"})


# ── Pure helpers (unit-testable, kept here for backward compatibility) ─────────

def _is_morning() -> bool:
    return datetime.now().hour < MORNING_CUTOFF_HOUR


def _build_system_prompt(goals: list, db=None) -> str:
    """Inject current goal state into the system prompt."""
    from app.intelligence.week_context import build_week_context_lines

    active = [g for g in goals if g.state not in TERMINAL_STATES]
    primacy = next((g for g in active if g.state == GoalState.primacy), None)

    lines = [
        "You are planA — a personal goal tracking companion.",
        "",
        "Surface reality honestly. Acknowledge drift or missed commitments when you see them.",
        "Never tell the user what to do. Never recommend dropping or pausing a goal.",
        "Ask one short, direct question at a time.",
        "When structured data has been provided earlier in this conversation it came from "
        "real database queries and is accurate. Do not retract or second-guess it.",
        "",
    ]

    lines.extend(build_week_context_lines(goals, db=db))

    if primacy:
        lines.append(f"Primacy goal (inviolable — no sacrifice expected): {primacy.title}")
        lines.append("")

    if active:
        lines.append("Active goals:")
        for g in active:
            lines.append(f"  [{g.state.value}] {g.title}")
    else:
        lines.append("No active goals.")

    return "\n".join(lines)


def _stub_response(intent: str, is_morning: bool) -> str:
    if is_morning or intent == "morning_checkin":
        return (
            "Good morning. How are you feeling today — physically and mentally? "
            "Good, neutral, or flat?"
        )
    return {
        "progress_capture": "Got it. Which goal was that for?",
        "physical_state": "Noted. Is this affecting today's training?",
        "illness_log": "Got it. How long have you been feeling this way?",
        "metric_log": "Logged.",
        "goal_query": "Ask me again with Claude enabled for real goal analysis.",
        "activity_query": "Activity lookup requires Claude enabled.",
        "sacrifice_log": "Sacrifice logged.",
        "milestone_complete": "Milestone marked.",
        "goal_state_change": "State change processed.",
        "free_response": "Tell me more.",
    }.get(intent, "Got it.")


def _write_capture(db, intent: str, text: str) -> None:
    """Persist a MetricReading for physical/illness/metric intents.

    Kept here for backward compatibility — tests patch app.bot.handler.capture_service.
    """
    if intent not in _CAPTURE_INTENTS:
        return
    try:
        if intent == "physical_state":
            capture_service.record_physical_state(db, text)
        elif intent == "illness_log":
            capture_service.record_illness(db, text)
        elif intent == "metric_log":
            capture_service.record_metric(db, text)
        logger.debug(f"Capture persisted: intent={intent}")
    except Exception as e:
        logger.error(f"Capture persist failed for intent={intent}: {e}")


def _is_affirmative(text: str) -> bool:
    low = text.lower().strip()
    return any(w in low for w in _YES_WORDS)


def _is_negative(text: str) -> bool:
    low = text.lower().strip()
    return any(w in low for w in _NO_WORDS)


# ── PTB handlers ───────────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    if not text:
        return

    logger.info(f"Message: '{text[:80]}'")

    is_morning = _is_morning()
    redis_client = get_redis()
    claude_client = get_client()

    intent, confidence = await asyncio.to_thread(
        classify_intent_with_confidence, text, is_morning, claude_client
    )
    original_intent = intent
    if is_morning and intent != "free_response":
        intent = "morning_checkin"
    logger.info(f"Intent={intent} (original={original_intent}) confidence={confidence:.2f} morning={is_morning}")

    messages = session_mgr.append_message(redis_client, "user", text)

    db = SessionLocal()
    try:
        goals = db.query(Goal).all()
        pending = session_mgr.get_pending_capture(redis_client)
        pending_alert = session_mgr.get_pending_alert(redis_client)

        response_text = None

        # Fix 2: check for pending drift/fade alert acknowledgement before normal routing.
        if pending_alert:
            if _is_affirmative(text):
                session_mgr.clear_pending_alert(redis_client)
                alert_goal = db.query(Goal).filter(
                    Goal.id == pending_alert.get("goal_id")
                ).first()
                if alert_goal:
                    response_text = await asyncio.to_thread(
                        goal_query_module.build_response,
                        "Give me a full status update for this goal.",
                        [alert_goal], db, claude_client,
                    )
                else:
                    response_text = "That goal no longer exists."
                logger.debug(f"Alert acknowledged for goal_id={pending_alert.get('goal_id')}")
            elif _is_negative(text):
                session_mgr.clear_pending_alert(redis_client)
                response_text = "Noted."
                logger.info(f"Alert dismissed for goal_id={pending_alert.get('goal_id')}")

        if response_text is None:
            handler = REGISTRY.get(intent)
            ctx = HandlerContext(
                text=text,
                intent=intent,
                original_intent=original_intent,
                is_morning=is_morning,
                goals=goals,
                db=db,
                claude_client=claude_client,
                redis_client=redis_client,
                pending_capture=pending,
                pending_alert=pending_alert,
                messages=messages,
                confidence=confidence,
            )
            if not handler.uses_pending_capture():
                session_mgr.clear_pending_capture(redis_client)
            response_text = await handler.handle(ctx)

    finally:
        db.close()

    session_mgr.append_message(redis_client, "assistant", response_text)
    await update.message.reply_text(response_text)
    logger.info(f"Sent: '{response_text[:80]}'")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Unhandled bot error: {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("Something went wrong. Try again.")


def create_application(token: str) -> Application:
    """Build the PTB Application with all handlers wired up."""
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    return app
