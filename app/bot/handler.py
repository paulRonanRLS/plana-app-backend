"""Telegram message handler — full pipeline for every incoming message.

Flow per message:
  1. Detect morning window (before 10am local time)
  2. Classify intent + confidence (Claude JSON response or keyword stub)
  3. Save original_intent; apply morning_checkin override if before 10am
  4. Append user message to Redis session
  5. Open DB; load active goals (always needed for goal-title matching)
  6. Check pending_alert (drift/fade acknowledgement) — yes/no short-circuits routing
  7. Routing:
       a. free_response + pending capture → try keyword then title match
       b. progress_capture → match by keywords/title, or set pending with clarification
       c. sacrifice_log → extract resource, match goal, write Sacrifice record
       d. milestone_complete → match milestone title, mark achieved, report next
       e. goal_state_change → extract state + goal, call lifecycle service
       f. everything else → clear stale pending, write non-progress captures
          (using original_intent so pre-10am metric/physical logs are preserved),
          route to specialised Claude paths or generic response
  8. Append assistant response to session
  9. Reply to user
"""

import asyncio
import logging
from datetime import datetime

from fastapi import HTTPException
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
from app.models.milestone import MilestoneState
from app.models.sacrifice import Sacrifice as SacrificeModel
from app.services import capture as capture_service
from app.services import goal as goal_service
from app.services.goal import TERMINAL_STATES
from app.services.milestone import list_milestones, update_milestone
from app.services.resource import get_resource_tension
from app.services.activity import parse_date_reference, query_activities, _parse_activity_type

logger = logging.getLogger(__name__)

MORNING_CUTOFF_HOUR = 10
MAX_HISTORY = 20  # messages retained in context window

# Physical/illness/metric captures are always written on classification.
# progress_capture is handled separately (goal matching + pending flow).
_CAPTURE_INTENTS = frozenset({"physical_state", "illness_log", "metric_log"})

# Words that signal "yes, review it" in response to a drift/fade alert.
_YES_WORDS = frozenset({"yes", "review", "yeah", "yep", "please", "sure", "ok", "okay"})
# Words that signal "no, dismiss" in response to a drift/fade alert.
_NO_WORDS = frozenset({"no", "not now", "dismiss", "nope", "skip", "later"})


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
        "sacrifice_log": "Sacrifice logged.",
        "milestone_complete": "Milestone marked.",
        "goal_state_change": "State change processed.",
        "free_response": "Tell me more.",
    }.get(intent, "Got it.")


def _write_capture(db, intent: str, text: str) -> None:
    """Persist a MetricReading for physical/illness/metric intents.

    progress_capture and the three new intents are excluded — they have their own
    routing with direct DB writes.
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
    # FIX 1: save original intent before the morning override so _write_capture
    # can still persist physical_state/illness_log/metric_log captures that arrive
    # before 10am — they should write to the DB AND fold into the check-in context.
    original_intent = intent
    if is_morning and intent != "free_response":
        intent = "morning_checkin"
    logger.info(f"Intent={intent} (original={original_intent}) confidence={confidence:.2f} morning={is_morning}")

    messages = session_mgr.append_message(redis_client, "user", text)

    db = SessionLocal()
    try:
        goals = db.query(Goal).all()
        active_goals = [g for g in goals if g.state not in TERMINAL_STATES]
        pending = session_mgr.get_pending_capture(redis_client)

        response_text = None

        # FIX 2: check for pending drift/fade alert acknowledgement before normal routing.
        # If a yes/no answer is detected, short-circuit and return a goal summary or dismissal.
        pending_alert = session_mgr.get_pending_alert(redis_client)
        if pending_alert:
            if _is_affirmative(text):
                session_mgr.clear_pending_alert(redis_client)
                alert_goal_id = pending_alert.get("goal_id")
                alert_goal = db.query(Goal).filter(Goal.id == alert_goal_id).first()
                if alert_goal:
                    response_text = await asyncio.to_thread(
                        goal_query_module.build_response,
                        "Give me a full status update for this goal.",
                        [alert_goal], db, claude_client,
                    )
                else:
                    response_text = "That goal no longer exists."
                logger.debug(f"Alert acknowledged (yes) for goal_id={alert_goal_id}")
            elif _is_negative(text):
                session_mgr.clear_pending_alert(redis_client)
                response_text = "Noted."
                logger.info(f"Alert dismissed for goal_id={pending_alert.get('goal_id')}")

        # ── Intent routing ─────────────────────────────────────────────────────
        if response_text is None:
            if intent == "free_response" and pending:
                # FIX 3: try keyword match first, then title — mirrors the original
                # progress_capture path so capture_keywords are honoured at resolution.
                matched = (
                    capture_service.match_goal_by_keywords(text, active_goals)
                    or capture_service.match_goal_title(text, active_goals)
                )
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
                session_mgr.clear_pending_capture(redis_client)
                matched = (
                    capture_service.match_goal_by_keywords(text, active_goals)
                    or capture_service.match_goal_title(text, active_goals)
                )
                if matched:
                    capture_service.record_progress(db, text, goal_id=matched.id)
                    response_text = f"Logged for {matched.title}."
                    logger.debug(f"Direct capture: goal={matched.title}")
                elif confidence > 0.8:
                    session_mgr.set_pending_capture(redis_client, {"text": text, "confidence": confidence})
                    response_text = "Got it. Which goal was that for?"
                else:
                    session_mgr.set_pending_capture(redis_client, {"text": text, "confidence": confidence})
                    response_text = "Which goal was that for?"

            # FIX 4a: sacrifice_log — extract resource, match goal, write Sacrifice row.
            elif intent == "sacrifice_log":
                session_mgr.clear_pending_capture(redis_client)
                resource = capture_service.extract_resource_from_text(text)
                matched = (
                    capture_service.match_goal_by_keywords(text, active_goals)
                    or capture_service.match_goal_title(text, active_goals)
                )
                if matched:
                    capture_service.record_sacrifice(db, matched.id, resource, text)
                    count = (
                        db.query(SacrificeModel)
                        .filter(SacrificeModel.goal_id == matched.id)
                        .count()
                    )
                    response_text = (
                        f"Logged — sacrifice attributed to {resource.value}. "
                        f"{matched.title} sacrifice count now {count}."
                    )
                    logger.debug(f"Sacrifice logged: goal={matched.title} resource={resource.value}")
                else:
                    response_text = "Sacrifice noted — which goal did it affect?"
                    logger.debug("Sacrifice: no goal matched")

            # FIX 4b: milestone_complete — match milestone title, mark achieved.
            elif intent == "milestone_complete":
                session_mgr.clear_pending_capture(redis_client)
                all_milestones = []
                for g in active_goals:
                    all_milestones.extend(list_milestones(db, g.id))
                # Only match against non-terminal milestones
                open_milestones = [
                    m for m in all_milestones
                    if m.state not in (MilestoneState.achieved, MilestoneState.missed)
                ]
                matched_ms = capture_service.match_milestone_title(text, open_milestones)
                if matched_ms:
                    update_milestone(
                        db, matched_ms.goal_id, matched_ms.id,
                        {"state": MilestoneState.achieved},
                    )
                    # Find next open milestone for the same goal
                    remaining = sorted(
                        [m for m in open_milestones
                         if m.goal_id == matched_ms.goal_id and m.id != matched_ms.id],
                        key=lambda m: m.sequence,
                    )
                    if remaining:
                        nxt = remaining[0]
                        due = f" — due {nxt.target_date.isoformat()}" if nxt.target_date else ""
                        response_text = f"Milestone marked complete. {nxt.title} is next{due}."
                    else:
                        response_text = "Milestone marked complete. No more pending milestones for that goal."
                    logger.debug(f"Milestone achieved: {matched_ms.title}")
                else:
                    response_text = "I couldn't match that to a milestone — which one did you complete?"
                    logger.debug("Milestone complete: no milestone matched")

            # FIX 4c: goal_state_change — extract target state and goal, call lifecycle service.
            elif intent == "goal_state_change":
                session_mgr.clear_pending_capture(redis_client)
                target_state = capture_service.extract_target_state_from_text(text)
                matched = (
                    capture_service.match_goal_by_keywords(text, active_goals)
                    or capture_service.match_goal_title(text, active_goals)
                )
                if matched and target_state:
                    try:
                        if target_state == "primacy":
                            goal_service.set_primacy(db, matched.id)
                            response_text = f"Done — {matched.title} is now planA."
                        elif target_state == "active":
                            goal_service.activate_goal(db, matched.id)
                            response_text = f"Done — {matched.title} is now active."
                        elif target_state == "subordinate":
                            goal_service.set_subordinate(db, matched.id)
                            response_text = f"Done — {matched.title} is now subordinate."
                        elif target_state == "drifting":
                            goal_service.mark_drifting(db, matched.id)
                            response_text = f"Done — {matched.title} flagged as drifting."
                        logger.debug(f"State change: goal={matched.title} → {target_state}")
                    except HTTPException as exc:
                        response_text = f"Couldn't change state: {exc.detail}"
                        logger.warning(f"State change failed: {exc.detail}")
                elif not matched:
                    response_text = "Which goal did you want to change the state of?"
                else:
                    response_text = "What state? (planA, active, subordinate)"

            else:
                # All other intents (morning_checkin, physical_state, illness_log,
                # metric_log, goal_query, activity_query, free_response without pending).
                if pending:
                    session_mgr.clear_pending_capture(redis_client)

        # ── Normal routing (when response_text is still None) ──────────────────
        if response_text is None:
            # FIX 1: use original_intent so physical_state/illness_log/metric_log
            # captures sent before 10am still write to the DB even though intent
            # has been overridden to morning_checkin.
            _write_capture(db, original_intent, text)

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
