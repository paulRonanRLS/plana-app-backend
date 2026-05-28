"""Telegram message handler — full pipeline for every incoming message.

Flow per message:
  1. Detect morning window (before 10am local time)
  2. Classify intent + confidence (Claude JSON response or keyword stub)
  3. Force intent = morning_checkin when before 10am and not mid-conversation
  4. Append user message to Redis session
  5. Open DB; load active goals (always needed for goal-title matching)
  6. Routing:
       a. free_response + pending capture → try to resolve against named goal
       b. progress_capture → match explicit goal title, or save as pending with
          a question tailored to confidence level (>0.8: brief, ≤0.8: explicit)
       c. everything else → clear stale pending, write non-progress captures,
          route to specialised Claude paths or generic response
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
from app.bot.intent import classify_intent_with_confidence
from app.core.claude_client import get_client
from app.core.redis_client import get_redis
from app.database import SessionLocal
from app.intelligence import checkin as checkin_module
from app.intelligence import activity_query as activity_query_module
from app.intelligence import goal_query as goal_query_module
from app.models.goal import Goal, GoalState
from app.services import capture as capture_service
from app.services.goal import TERMINAL_STATES
from app.services.resource import get_resource_tension
from app.services.activity import parse_date_reference, query_activities, _parse_activity_type

logger = logging.getLogger(__name__)

MORNING_CUTOFF_HOUR = 10
MAX_HISTORY = 20  # messages retained in context window

# Physical/illness/metric captures are always written on classification.
# progress_capture is handled separately (goal matching + pending flow).
_CAPTURE_INTENTS = frozenset({"physical_state", "illness_log", "metric_log"})


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
        "When structured data has been provided earlier in this conversation it came from "
        "real database queries and is accurate. Do not retract or second-guess it.",
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
        "progress_capture": "Got it. Which goal was that for?",
        "physical_state": "Noted. Is this affecting today's training?",
        "illness_log": "Got it. How long have you been feeling this way?",
        "metric_log": "Logged.",
        "goal_query": "Ask me again with Claude enabled for real goal analysis.",
        "activity_query": "Activity lookup requires Claude enabled.",
        "free_response": "Tell me more.",
    }.get(intent, "Got it.")


def _write_capture(db, intent: str, text: str) -> None:
    """Persist a MetricReading for physical/illness/metric intents.

    progress_capture is excluded — it is handled via the goal-matching flow.
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

    intent, confidence = classify_intent_with_confidence(text, is_morning, claude_client)
    if is_morning and intent != "free_response":
        intent = "morning_checkin"
    logger.info(f"Intent={intent} confidence={confidence:.2f} morning={is_morning}")

    messages = session_mgr.append_message(redis_client, "user", text)

    db = SessionLocal()
    try:
        goals = db.query(Goal).all()
        active_goals = [g for g in goals if g.state not in TERMINAL_STATES]
        pending = session_mgr.get_pending_capture(redis_client)

        # response_text=None means "fall through to normal routing below".
        response_text = None

        if intent == "free_response" and pending:
            # The user is replying to our "which goal?" question.
            matched = capture_service.match_goal_title(text, active_goals)
            if matched:
                capture_service.record_progress(db, pending["text"], goal_id=matched.id)
                session_mgr.clear_pending_capture(redis_client)
                response_text = f"Logged for {matched.title}."
                logger.debug(f"Pending capture resolved: goal={matched.title}")
            else:
                # Can't resolve — drop the pending and treat as regular free_response.
                session_mgr.clear_pending_capture(redis_client)
                logger.debug("Pending capture unresolved — dropping, treating as free_response")

        elif intent == "progress_capture":
            # Always supersede any stale pending capture.
            session_mgr.clear_pending_capture(redis_client)
            matched = capture_service.match_goal_title(text, active_goals)
            if matched:
                # Explicit goal title in the message — log immediately, no confirmation needed.
                capture_service.record_progress(db, text, goal_id=matched.id)
                response_text = f"Logged for {matched.title}."
                logger.debug(f"Direct capture: goal={matched.title}")
            elif confidence > 0.8:
                # High confidence it's a capture, just needs a goal.
                session_mgr.set_pending_capture(redis_client, {"text": text, "confidence": confidence})
                response_text = "Got it. Which goal was that for?"
            else:
                # Lower confidence — ask more explicitly.
                session_mgr.set_pending_capture(redis_client, {"text": text, "confidence": confidence})
                response_text = "Which goal was that for?"

        else:
            # Any other intent clears a stale pending capture.
            if pending:
                session_mgr.clear_pending_capture(redis_client)

        # ── Normal routing (when response_text is still None) ──────────────────
        if response_text is None:
            _write_capture(db, intent, text)

            if claude_client is not None:
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
                        db=db,
                    )
                elif intent == "activity_query":
                    start, end = parse_date_reference(text)
                    activity_type = _parse_activity_type(text)
                    logger.debug(
                        f"activity_query: type={activity_type!r} "
                        f"range={start.date()}–{end.date()}"
                    )
                    activities = await asyncio.to_thread(
                        query_activities, db, start, end, activity_type
                    )
                    logger.debug(f"activity_query: found {len(activities)} activities")
                    response_text = await asyncio.to_thread(
                        activity_query_module.build_response, text, activities, claude_client
                    )
                elif intent == "goal_query":
                    response_text = await asyncio.to_thread(
                        goal_query_module.build_response, text, goals, db, claude_client
                    )
                else:
                    system_prompt = _build_system_prompt(goals)
                    response_text = await _claude_response(messages, system_prompt, claude_client)
            else:
                response_text = _stub_response(intent, is_morning)

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
