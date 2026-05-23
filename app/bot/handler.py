"""Telegram message handler — full pipeline for every incoming message.

Flow per message:
  1. Detect morning window (before 10am local time)
  2. Classify intent (Claude or stub)
  3. Force intent = morning_checkin when before 10am and not mid-conversation
  4. Append user message to Redis session
  5. Load current goals → build system prompt
  6. Get response: real Claude conversation or stub
  7. Append assistant response to session
  8. Reply to user
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
from app.bot.intent import classify_intent
from app.core.claude_client import get_client
from app.core.redis_client import get_redis
from app.database import SessionLocal
from app.intelligence import checkin as checkin_module
from app.intelligence import activity_query as activity_query_module
from app.models.goal import Goal, GoalState
from app.services.goal import TERMINAL_STATES
from app.services.resource import get_resource_tension
from app.services.activity import parse_date_reference, query_activities, _parse_activity_type

logger = logging.getLogger(__name__)

MORNING_CUTOFF_HOUR = 10
MAX_HISTORY = 20  # messages retained in context window


# ── Pure helpers (unit-testable) ───────────────────────────────────────────────

def _is_morning() -> bool:
    """True when system local time is before 10am."""
    return datetime.now().hour < MORNING_CUTOFF_HOUR


def _build_system_prompt(goals: list) -> str:
    """Inject current goal state into the system prompt."""
    active = [g for g in goals if g.state not in TERMINAL_STATES]
    primacy = next((g for g in active if g.state == GoalState.primacy), None)

    lines = [
        "You are planA — a personal goal tracking companion.",
        "",
        "Surface reality honestly. Acknowledge drift or missed commitments when you see them.",
        "Never tell the user what to do. Never recommend dropping or pausing a goal.",
        "Ask one short, direct question at a time.",
        "",
    ]

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
        "progress_capture": "Good. What goal was that for?",
        "physical_state": "Noted. Is this affecting today's training?",
        "illness_log": "Got it. How long have you been feeling this way?",
        "metric_log": "Logged.",
        "goal_query": "Ask me again with Claude enabled for real goal analysis.",
        "activity_query": "Activity lookup requires Claude enabled.",
        "free_response": "Tell me more.",
    }.get(intent, "Got it.")


# ── Response generation ────────────────────────────────────────────────────────

async def _claude_response(
    messages: list[dict],
    system_prompt: str,
    client,
) -> str:
    """Call Claude in a thread so we don't block the event loop."""
    try:
        trimmed = messages[-MAX_HISTORY:]
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system_prompt,
            messages=trimmed,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude response failed: {e}")
        return "Something went wrong — try again in a moment."


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

    intent = classify_intent(text, is_morning, claude_client)
    if is_morning and intent != "free_response":
        intent = "morning_checkin"
    logger.info(f"Intent={intent} morning={is_morning}")

    messages = session_mgr.append_message(redis_client, "user", text)

    if claude_client is not None:
        db = SessionLocal()
        try:
            goals = db.query(Goal).all()
            if intent == "morning_checkin":
                tension = get_resource_tension(db)
                response_text = await asyncio.to_thread(
                    checkin_module.build_response,
                    messages,
                    goals,
                    claude_client,
                    time_envelope_hours=tension.time_envelope_hours,
                    recovery_envelope_tss=tension.recovery_envelope_tss,
                    time_ratio=tension.time_ratio,
                    recovery_ratio=tension.recovery_ratio,
                    attention_count=tension.attention_count,
                )
            elif intent == "activity_query":
                start, end = parse_date_reference(text)
                activity_type = _parse_activity_type(text)
                activities = await asyncio.to_thread(
                    query_activities, db, start, end, activity_type
                )
                response_text = await asyncio.to_thread(
                    activity_query_module.build_response, text, activities, claude_client
                )
            else:
                system_prompt = _build_system_prompt(goals)
                response_text = await _claude_response(messages, system_prompt, claude_client)
        finally:
            db.close()
    else:
        response_text = _stub_response(intent, is_morning)

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
