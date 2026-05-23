"""Intent classification for incoming Telegram messages.

CLAUDE_ENABLED=true  → one-shot Claude call; expects exactly one label back.
CLAUDE_ENABLED=false → rule-based keyword stub, good enough for testing.
"""

import logging
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

INTENTS = frozenset({
    "morning_checkin",
    "progress_capture",
    "physical_state",
    "illness_log",
    "metric_log",
    "goal_query",
    "free_response",
})

_USER_TEMPLATE = """\
Classify this message into exactly one intent:

  morning_checkin  — waking report: subjective feel, energy, sleep quality
  progress_capture — activity or work done toward a specific goal
  physical_state   — physical symptom: sore, fatigued, injured, niggles
  illness_log      — illness start, progression, or recovery note
  metric_log       — a specific measurable value (weight, alcohol units, etc.)
  goal_query       — question about goal status, progress, or resources
  free_response    — continuation of conversation or anything else

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
            model="claude-sonnet-4-20250514",
            max_tokens=20,
            messages=[{"role": "user", "content": _USER_TEMPLATE.format(text=text)}],
        )
        label = resp.content[0].text.strip().lower()
        if label in INTENTS:
            return label
        logger.warning(f"Unexpected intent label '{label}' from Claude — using stub")
        return _stub_classify(text, is_morning)
    except Exception as e:
        logger.warning(f"Intent classification error: {e} — using stub")
        return _stub_classify(text, is_morning)


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
    if any(w in low for w in ("ran", "cycled", "trained", "wrote", "cooked", "did", "finished", "completed")):
        return "progress_capture"
    return "free_response"
