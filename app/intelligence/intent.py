"""Context-aware intent classification.

Extends the bot-level classifier (app/bot/intent.py) with full goal state
context injected into the classification prompt and a confidence score.

The bot (app/bot/intent.py) handles fast, low-context classification.
This module is for cases requiring higher accuracy with richer context.
"""

import logging

from app.bot.intent import INTENTS, _stub_classify
from app.services.goal import TERMINAL_STATES

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 50


def _goals_context(goals: list) -> str:
    """Brief goal list for injection into classification prompt."""
    active = [g for g in goals if g.state not in TERMINAL_STATES]
    if not active:
        return "No active goals."
    return "Active goals: " + ", ".join(
        f"{g.title} [{g.state.value}]" for g in active
    )


def classify(
    text: str,
    goals: list,
    is_morning: bool,
    client,
) -> dict:
    """Classify intent with goal context.

    Returns {'intent': str, 'confidence': float}.

    Confidence is 1.0 for is_morning (forced), 0.9 for Claude match,
    0.5 for stub fallback or unrecognised Claude label.
    Falls back to stub when client is None or on error.
    """
    if is_morning:
        return {"intent": "morning_checkin", "confidence": 1.0}

    if client is None:
        return {"intent": _stub_classify(text, is_morning=False), "confidence": 0.5}

    goals_ctx = _goals_context(goals)
    prompt = (
        f"{goals_ctx}\n\n"
        "Classify this message into exactly one intent label.\n"
        "Labels: morning_checkin, progress_capture, physical_state, "
        "illness_log, metric_log, goal_query, activity_query, free_response\n"
        f"Message: {text}\n\n"
        "Reply with ONLY the label."
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        label = resp.content[0].text.strip().lower()
        if label in INTENTS:
            return {"intent": label, "confidence": 0.9}
        intent = _stub_classify(text, is_morning=False)
        return {"intent": intent, "confidence": 0.5}
    except Exception as e:
        logger.error(f"Context-aware classification failed: {e}")
        intent = _stub_classify(text, is_morning=False)
        return {"intent": intent, "confidence": 0.5}
