"""Redis-backed conversation session for the Telegram bot.

Single user app — one fixed key, TTL reset on every interaction.
Messages stored as JSON list of {"role": ..., "content": ...} dicts —
the exact format Claude's messages API expects.

Pending capture state (bot:pending_capture) holds a progress_capture that
is waiting for the user to name a goal.  It shares the same TTL as the session.
"""

import json
import logging
from typing import Optional

import redis

logger = logging.getLogger(__name__)

SESSION_KEY = "bot:session"
PENDING_CAPTURE_KEY = "bot:pending_capture"
SESSION_TTL = 1800  # 30 minutes in seconds


def get_session(client: Optional[redis.Redis]) -> list[dict]:
    """Return stored messages, or [] if no session / Redis unavailable."""
    if client is None:
        return []
    try:
        raw = client.get(SESSION_KEY)
        return json.loads(raw) if raw else []
    except Exception as e:
        logger.warning(f"Session get failed: {e}")
        return []


def save_session(client: Optional[redis.Redis], messages: list[dict]) -> None:
    """Persist messages and reset TTL."""
    if client is None:
        return
    try:
        client.setex(SESSION_KEY, SESSION_TTL, json.dumps(messages))
    except Exception as e:
        logger.warning(f"Session save failed: {e}")


def append_message(
    client: Optional[redis.Redis],
    role: str,
    content: str,
) -> list[dict]:
    """Append one message to the session and return the updated list."""
    messages = get_session(client)
    messages.append({"role": role, "content": content})
    save_session(client, messages)
    return messages


def clear_session(client: Optional[redis.Redis]) -> None:
    """Delete the session key (e.g. after a natural conversation end)."""
    if client is None:
        return
    try:
        client.delete(SESSION_KEY)
    except Exception as e:
        logger.warning(f"Session clear failed: {e}")


# ── Pending capture ────────────────────────────────────────────────────────────

def set_pending_capture(client: Optional[redis.Redis], data: dict) -> None:
    """Store a pending progress capture awaiting goal confirmation."""
    if client is None:
        return
    try:
        client.setex(PENDING_CAPTURE_KEY, SESSION_TTL, json.dumps(data))
    except Exception as e:
        logger.warning(f"Pending capture save failed: {e}")


def get_pending_capture(client: Optional[redis.Redis]) -> Optional[dict]:
    """Return the pending capture dict, or None if none exists."""
    if client is None:
        return None
    try:
        raw = client.get(PENDING_CAPTURE_KEY)
        return json.loads(raw) if raw else None
    except Exception as e:
        logger.warning(f"Pending capture get failed: {e}")
        return None


def clear_pending_capture(client: Optional[redis.Redis]) -> None:
    """Delete the pending capture key."""
    if client is None:
        return
    try:
        client.delete(PENDING_CAPTURE_KEY)
    except Exception as e:
        logger.warning(f"Pending capture clear failed: {e}")
