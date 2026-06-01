"""Intent classification for incoming Telegram messages.

CLAUDE_ENABLED=true  → one-shot Claude call; expects exactly one label back.
CLAUDE_ENABLED=false → rule-based keyword stub, good enough for testing.
"""

import json
import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

from app.bot.handlers import REGISTRY  # noqa: E402 (import after package-level setup)

INTENTS = REGISTRY.all_intents()

_USER_TEMPLATE = """\
Classify this message into exactly one intent:

  morning_checkin   — waking report: subjective feel, energy, sleep quality
  progress_capture  — reporting an activity or work just done toward a goal
  physical_state    — physical symptom: sore, fatigued, injured, niggles
  illness_log       — illness start, progression, or recovery note
  metric_log        — a specific measurable value (weight, alcohol units, etc.)
  goal_query        — question about goal status, progress, or resources
  activity_query    — question about past workouts, rides, runs, or training sessions (e.g. "what was my ride on Sunday", "how far did I run last week")
  sacrifice_log     — reporting a skipped commitment or deprioritised goal (e.g. "sacrificed my run for work", "skipped training because of meetings")
  milestone_complete — reporting completion of a specific milestone (e.g. "just hit my foundation milestone", "finished the 18km long run milestone")
  goal_state_change  — requesting a change to a goal's priority state (e.g. "set cycling as my planA", "make training subordinate")
  free_response     — continuation of conversation or anything else

Message: {text}

Reply with exactly one label — nothing else."""


def classify_intent(
    text: str,
    is_morning: bool,
    client: Optional[anthropic.Anthropic],
) -> str:
    """Classify the intent of an incoming message.

    Returns one label from INTENTS. Falls back to the keyword stub on any error.
    """
    if client is None:
        return _stub_classify(text, is_morning)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=20,
            messages=[{"role": "user", "content": _USER_TEMPLATE.format(text=text)}],
            timeout=15.0,
        )
        label = resp.content[0].text.strip().lower()
        if label in INTENTS:
            return label
        logger.warning(f"Unexpected intent label '{label}' from Claude — using stub")
        return _stub_classify(text, is_morning)
    except Exception as e:
        logger.warning(f"Intent classification error: {e} — using stub")
        return _stub_classify(text, is_morning)


_USER_TEMPLATE_CONFIDENCE = """\
Classify this message into exactly one intent and rate your confidence.

  morning_checkin   — waking report: subjective feel, energy, sleep quality
  progress_capture  — reporting an activity or work just done toward a goal
  physical_state    — physical symptom: sore, fatigued, injured, niggles
  illness_log       — illness start, progression, or recovery note
  metric_log        — a specific measurable value (weight, alcohol units, etc.)
  goal_query        — question about goal status, progress, or resources
  activity_query    — question about past workouts, rides, runs, or training sessions
  sacrifice_log     — reporting a skipped commitment or deprioritised goal
  milestone_complete — reporting completion of a specific milestone
  goal_state_change  — requesting a change to a goal's priority state
  free_response     — continuation of conversation or anything else

Message: {text}

Reply with JSON only, no other text: {{"intent": "<label>", "confidence": <0.0-1.0>}}"""

# Default confidence values for the keyword stub — used when Claude is unavailable.
_STUB_CONFIDENCE: dict[str, float] = {
    "morning_checkin": 1.0,
    "physical_state": 0.95,
    "illness_log": 0.95,
    "metric_log": 0.95,
    "goal_query": 0.9,
    "activity_query": 0.9,
    "sacrifice_log": 0.9,
    "milestone_complete": 0.9,
    "goal_state_change": 0.9,
    "progress_capture": 0.85,
    "free_response": 0.5,
}


def classify_intent_with_confidence(
    text: str,
    is_morning: bool,
    client: Optional[anthropic.Anthropic],
) -> tuple[str, float]:
    """Classify intent and return (label, confidence).

    Uses a single Claude call returning JSON when Claude is available.
    Falls back to the keyword stub with fixed confidence values on any error.
    """
    if client is None:
        intent = _stub_classify(text, is_morning)
        return intent, _STUB_CONFIDENCE.get(intent, 0.7)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=40,
            messages=[{"role": "user", "content": _USER_TEMPLATE_CONFIDENCE.format(text=text)}],
            timeout=15.0,
        )
        raw = resp.content[0].text.strip()
        data = json.loads(raw)
        label = data.get("intent", "").lower()
        confidence = float(data.get("confidence", 0.7))
        if label in INTENTS:
            return label, confidence
        logger.warning(f"Unexpected intent label '{label}' from Claude — using stub")
    except Exception as e:
        logger.warning(f"Intent classification error: {e} — using stub")
    intent = _stub_classify(text, is_morning)
    return intent, _STUB_CONFIDENCE.get(intent, 0.7)


def _stub_classify(text: str, is_morning: bool) -> str:
    """Rule-based fallback when Claude is unavailable."""
    if is_morning:
        return "morning_checkin"
    low = text.lower()
    if any(w in low for w in ("sore", "ache", "pain", "tired", "fatigue", "niggle")):
        return "physical_state"
    if any(w in low for w in ("sick", "ill", "cold", "flu", "fever", "recover")):
        return "illness_log"
    if any(w in low for w in ("goal", "status", "progress", "tension", "resource")):
        return "goal_query"
    if any(w in low for w in ("kg", "lb", "weight", "unit", "alcohol", "drank")):
        return "metric_log"
    # goal_state_change: explicit priority/state change requests
    _state_change_markers = ("set as my plana", "set as plana", "make my plana", "as my plana",
                             "as my priority goal", "set as priority", "make subordinate",
                             "subordinate now", "back to active", "set active", "set as active")
    if any(m in low for m in _state_change_markers):
        return "goal_state_change"
    # sacrifice_log: skipped or missed commitment — check before progress_capture
    _sacrifice_markers = ("sacrificed", "skipped my", "missed my", "had to skip",
                          "couldn't do", "gave up my", "skipped training", "skipped the")
    if any(m in low for m in _sacrifice_markers):
        return "sacrifice_log"
    # milestone_complete: milestone keyword with completion verb — before progress_capture
    _completion_verbs = ("completed", "finished", "hit my", "done with", "achieved")
    if any(v in low for v in _completion_verbs) and "milestone" in low:
        return "milestone_complete"
    _activity_keywords = ("ride", "run", "rode", "ran", "swim", "swam", "workout", "training", "session")
    _temporal_keywords = ("yesterday", "last", "sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "week", "today", "this morning")
    _query_starters = ("how", "what", "show", "tell", "did", "was", "were")
    if any(w in low for w in _activity_keywords) and any(w in low for w in _temporal_keywords):
        # Only classify as activity_query when the message reads as a question/lookup,
        # not a past-tense progress report ("ran 10k this morning" is a capture, not a query).
        if any(low.startswith(q) for q in _query_starters):
            return "activity_query"
    if any(w in low for w in ("ran", "cycled", "trained", "wrote", "cooked", "did", "finished", "completed")):
        return "progress_capture"
    return "free_response"
