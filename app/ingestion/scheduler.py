"""APScheduler setup for Garmin and Strava ingestion jobs.

Garmin schedule:
  - Every 15 minutes from 06:00 to 09:59 local time (catches overnight data as
    it appears on Garmin Connect)
  - Once at 10:00 local time as a backstop if data still hasn't synced

Strava schedule:
  - Every 30 minutes, all day

Both jobs catch all exceptions and log them — a failed sync never crashes the
server. Jobs are idempotent, so re-running them is always safe.
"""

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
    from app.ingestion.strava import sync_strava
    db = SessionLocal()
    try:
        rows = sync_strava(db)
        if rows:
            logger.info(f"Strava job: stored {len(rows)} rows")
        else:
            logger.debug("Strava job: no new activities")
    except Exception as exc:
        logger.error(f"Strava job failed: {exc}", exc_info=True)
    finally:
        db.close()


def create_scheduler() -> BackgroundScheduler:
    """Build and configure the scheduler. Does not start it."""
    scheduler = BackgroundScheduler()

    # Garmin: every 15 min, 06:00–09:59 local time
    scheduler.add_job(
        _garmin_job,
        CronTrigger(hour="6-9", minute="*/15"),
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

    logger.info(
        "Scheduler configured: garmin_poll (06–09:45 ×15min), "
        "garmin_backstop (10:00), strava_poll (×30min)"
    )
    return scheduler
