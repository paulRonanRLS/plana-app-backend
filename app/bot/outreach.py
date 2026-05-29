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


async def send_drift_alert(bot, chat_id: int, goal, drift_event, *, redis_client=None) -> None:
    """Surface metric drift. Does not recommend any action.

    When redis_client is provided, stores a pending_alert so the next yes/no
    reply is routed to a goal summary rather than falling through to free_response.
    """
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
    if redis_client is not None:
        from app.bot import session as session_mgr
        session_mgr.set_pending_alert(redis_client, {"goal_id": goal.id, "alert_type": "drift"})
    logger.info(f"Drift alert sent for goal {goal.id} ({drift_event.days_outside_range}d outside range)")


async def send_fade_alert(bot, chat_id: int, goal, fade_event, *, redis_client=None) -> None:
    """Surface absence of goal activity. Does not recommend any action.

    When redis_client is provided, stores a pending_alert so the next yes/no
    reply is routed to a goal summary rather than falling through to free_response.
    """
    text = (
        f"No activity recorded for {goal.title} "
        f"in {fade_event.days_since_activity} days.\n\n"
        f"Is this goal still a priority?"
    )
    await bot.send_message(chat_id=chat_id, text=text)
    if redis_client is not None:
        from app.bot import session as session_mgr
        session_mgr.set_pending_alert(redis_client, {"goal_id": goal.id, "alert_type": "fade"})
    logger.info(f"Fade alert sent for goal {goal.id} ({fade_event.days_since_activity}d inactive)")


def _format_metric_value(value: float, metric: str) -> str:
    if metric == "distance_km":
        return f"{value:.1f}km"
    if metric == "duration_min":
        return f"{value:.0f}min"
    if metric == "tss":
        return f"{value:.0f} TSS"
    if metric == "count":
        return f"{value:.0f}"
    return str(value)


def _format_period_label(period: str) -> str:
    return {"week": "Weekly", "month": "Monthly", "lifetime": "Total"}.get(period, period.capitalize())


async def send_milestone_progress(bot, chat_id: int, update) -> None:
    """Notify user of milestone progress after an activity is logged."""
    activity_label = update.activity_type.capitalize()
    metric_str = _format_metric_value(update.metric_value, update.metric)

    if update.achieved:
        text = (
            f"{activity_label} logged — {metric_str}. "
            f"Milestone achieved: {update.milestone_title}."
        )
    else:
        current_str = _format_metric_value(update.current_value, update.metric)
        target_str = _format_metric_value(update.target_value, update.metric)
        period_label = _format_period_label(update.period)
        text = (
            f"{activity_label} logged — {metric_str}. "
            f"{period_label} {update.metric.replace('_', ' ')}: "
            f"{current_str} / {target_str}."
        )

    await bot.send_message(chat_id=chat_id, text=text)
    logger.info(f"Milestone progress sent: milestone={update.milestone_id} achieved={update.achieved}")


def dispatch_milestone_notifications(updates: list) -> None:
    """Send Telegram progress notifications from a synchronous context.

    No-ops when TELEGRAM_ENABLED=false or TELEGRAM_CHAT_ID is not set.
    """
    import asyncio
    from app.config import get_settings
    settings = get_settings()
    if not (settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id):
        return
    if not updates:
        return

    from telegram import Bot

    async def _send() -> None:
        async with Bot(token=settings.telegram_bot_token) as bot:
            for upd in updates:
                await send_milestone_progress(bot, settings.telegram_chat_id, upd)

    asyncio.run(_send())
