"""APScheduler setup for ingestion, drift, and fade jobs.

Garmin schedule:
  - Every hour at :00, 06:00–09:00 local time (catches overnight data)
  - Once at 10:00 local time as a backstop

Strava schedule:
  - Every 30 minutes, all day

Drift check:
  - Daily at 08:30 — detects perpetual goals outside their metric range for 3+ days

Fade check:
  - Every Monday at 09:00 — detects achievement goals with no activity for 14+ days

All jobs catch exceptions and log them — a failed job never crashes the server.
Jobs are idempotent, so re-running them is always safe.
"""

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.database import SessionLocal

logger = logging.getLogger(__name__)


def _garmin_job() -> None:
    """Scheduled wrapper around garmin.sync_garmin — creates its own DB session."""
    from app.ingestion.garmin import sync_garmin
    db = SessionLocal()
    try:
        rows = sync_garmin(db)
        if rows:
            logger.info(f"Garmin job: stored {len(rows)} readings")
        else:
            logger.debug("Garmin job: no new data")
    except Exception as exc:
        logger.error(f"Garmin job failed: {exc}", exc_info=True)
    finally:
        db.close()


def _strava_job() -> None:
    """Scheduled wrapper around strava.sync_strava — creates its own DB session."""
    from app.ingestion.strava import sync_strava, activity_dict_from_rows
    from app.services.milestone_progress import process_activity
    from app.bot.outreach import dispatch_milestone_notifications
    db = SessionLocal()
    try:
        rows = sync_strava(db)
        if rows:
            logger.info(f"Strava job: stored {len(rows)} rows")
        else:
            logger.debug("Strava job: no new activities")
            return
        all_updates = []
        for row in activity_dict_from_rows(rows):
            try:
                updates = process_activity(db, row)
                all_updates.extend(updates)
            except Exception as exc:
                logger.error(f"Strava job: milestone progress failed for activity: {exc}", exc_info=True)
        if all_updates:
            logger.info(f"Strava job: {len(all_updates)} milestone update(s)")
            dispatch_milestone_notifications(all_updates)
    except Exception as exc:
        logger.error(f"Strava job failed: {exc}", exc_info=True)
    finally:
        db.close()


def _drift_check_job() -> None:
    """Detect perpetual goals outside their metric range for 3+ consecutive days."""
    from app.services.drift import detect_drift
    db = SessionLocal()
    try:
        events = detect_drift(db)
        if not events:
            logger.debug("Drift check: no drift detected")
            return
        logger.info(f"Drift check: {len(events)} goal(s) drifting")
        _dispatch_drift_alerts(db, events)
    except Exception as exc:
        logger.error(f"Drift check failed: {exc}", exc_info=True)
    finally:
        db.close()


def _fade_check_job() -> None:
    """Detect achievement goals with no activity for 14+ days."""
    from app.services.fade import detect_fade
    db = SessionLocal()
    try:
        events = detect_fade(db)
        if not events:
            logger.debug("Fade check: no fade detected")
            return
        logger.info(f"Fade check: {len(events)} goal(s) fading")
        _dispatch_fade_alerts(db, events)
    except Exception as exc:
        logger.error(f"Fade check failed: {exc}", exc_info=True)
    finally:
        db.close()


def _dispatch_drift_alerts(db, events) -> None:
    from app.config import get_settings
    settings = get_settings()
    if not (settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id):
        return

    from telegram import Bot
    from app.bot.outreach import send_drift_alert
    from app.services.goal import get_goal
    from app.core.redis_client import get_redis

    redis_client = get_redis()

    async def _send() -> None:
        async with Bot(token=settings.telegram_bot_token) as bot:
            for event in events:
                goal = get_goal(db, event.goal_id)
                await send_drift_alert(bot, settings.telegram_chat_id, goal, event, redis_client=redis_client)

    asyncio.run(_send())


def _dispatch_fade_alerts(db, events) -> None:
    from app.config import get_settings
    settings = get_settings()
    if not (settings.telegram_enabled and settings.telegram_bot_token and settings.telegram_chat_id):
        return

    from telegram import Bot
    from app.bot.outreach import send_fade_alert
    from app.services.goal import get_goal
    from app.core.redis_client import get_redis

    redis_client = get_redis()

    async def _send() -> None:
        async with Bot(token=settings.telegram_bot_token) as bot:
            for event in events:
                goal = get_goal(db, event.goal_id)
                await send_fade_alert(bot, settings.telegram_chat_id, goal, event, redis_client=redis_client)

    asyncio.run(_send())


def create_scheduler() -> BackgroundScheduler:
    """Build and configure the scheduler. Does not start it."""
    scheduler = BackgroundScheduler()

    # Garmin: once per hour at :00, 06:00–09:00 local time
    scheduler.add_job(
        _garmin_job,
        CronTrigger(hour="6-9", minute=0),
        id="garmin_poll",
        name="Garmin overnight data poll",
        replace_existing=True,
    )
    # Garmin: 10:00 backstop
    scheduler.add_job(
        _garmin_job,
        CronTrigger(hour=10, minute=0),
        id="garmin_backstop",
        name="Garmin 10am backstop",
        replace_existing=True,
    )
    # Strava: every 30 minutes
    scheduler.add_job(
        _strava_job,
        CronTrigger(minute="*/30"),
        id="strava_poll",
        name="Strava activity poll",
        replace_existing=True,
    )
    # Drift check: daily at 08:30
    scheduler.add_job(
        _drift_check_job,
        CronTrigger(hour=8, minute=30),
        id="drift_check",
        name="Drift detection — perpetual goals",
        replace_existing=True,
    )
    # Fade check: every Monday at 09:00
    scheduler.add_job(
        _fade_check_job,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="fade_check",
        name="Fade detection — achievement goals",
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured: garmin_poll (06:00–09:00 ×1h), "
        "garmin_backstop (10:00), strava_poll (×30min), "
        "drift_check (08:30 daily), fade_check (Mon 09:00)"
    )
    return scheduler
