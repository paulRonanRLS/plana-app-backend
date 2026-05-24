"""Proactive Telegram outreach for drift and fade alerts.

These functions surface reality to the user — they do NOT recommend any action.
Each message ends with a single yes/no question to invite acknowledgement.

Both functions are async (python-telegram-bot ≥ 20 requires it). Callers in
the sync APScheduler context should wrap with asyncio.run().
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Bot
    from app.models.goal import Goal
    from app.services.drift import DriftEvent
    from app.services.fade import FadeEvent

logger = logging.getLogger(__name__)


def _format_range(target_min, target_max) -> str:
    if target_min is not None and target_max is not None:
        return f"{target_min}–{target_max}"
    if target_min is not None:
        return f"≥{target_min}"
    if target_max is not None:
        return f"≤{target_max}"
    return "unknown"


async def send_drift_alert(bot, chat_id: int, goal, drift_event) -> None:
    """Surface metric drift. Does not recommend any action."""
    current_desc = (
        f"{drift_event.current_value:.1f}"
        if drift_event.current_value is not None
        else "no recent reading"
    )
    target_desc = _format_range(drift_event.target_min, drift_event.target_max)

    text = (
        f"{goal.title} has been outside its target range "
        f"for {drift_event.days_outside_range} consecutive days.\n\n"
        f"Metric: {drift_event.metric_type}\n"
        f"Current: {current_desc} — Target: {target_desc}\n\n"
        f"Do you want to review this goal?"
    )
    await bot.send_message(chat_id=chat_id, text=text)
    logger.info(f"Drift alert sent for goal {goal.id} ({drift_event.days_outside_range}d outside range)")


async def send_fade_alert(bot, chat_id: int, goal, fade_event) -> None:
    """Surface absence of goal activity. Does not recommend any action."""
    text = (
        f"No activity recorded for {goal.title} "
        f"in {fade_event.days_since_activity} days.\n\n"
        f"Is this goal still a priority?"
    )
    await bot.send_message(chat_id=chat_id, text=text)
    logger.info(f"Fade alert sent for goal {goal.id} ({fade_event.days_since_activity}d inactive)")
