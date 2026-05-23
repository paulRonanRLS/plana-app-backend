"""Milestone generation from goal metadata.

Generates a structured progression of milestones for a goal, taking into
account the goal's title, description, and target date.

Returns JSON-parsed list of {title, description, target_date} dicts.
Returns empty list in stub mode — milestone creation is always Claude-driven.
"""

import json
import logging
from datetime import date
from typing import Optional

from app.models.goal import Goal

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 600


def generate(goal: Goal, client, *, today: Optional[date] = None) -> list[dict]:
    """Generate a milestone progression for a goal.

    Returns a list of dicts with keys: title (str), description (str),
    target_date (str YYYY-MM-DD or None).

    Returns empty list when client is None (stub mode) or on any error.
    """
    if client is None:
        return []

    today = today or date.today()
    lines = [f"Goal: {goal.title}"]
    if goal.description:
        lines.append(f"Description: {goal.description}")
    lines.append(f"Target date: {goal.target_date}" if goal.target_date else "No fixed deadline")
    lines.append(f"Today: {today}")
    goal_context = "\n".join(lines)

    prompt = (
        "Generate a milestone progression for the following goal.\n"
        "Return a JSON array of objects with keys:\n"
        "  title (str), description (str), target_date (str YYYY-MM-DD or null)\n"
        "Generate 3 to 5 milestones that form a logical progression toward the goal. "
        "Be concrete and measurable. Return ONLY valid JSON, no other text.\n\n"
        f"{goal_context}"
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        milestones = json.loads(text)
        if not isinstance(milestones, list):
            return []
        return [m for m in milestones if isinstance(m, dict) and "title" in m]
    except Exception as e:
        logger.error(f"Milestone generation failed: {e}")
        return []
