"""Unit tests for app/ingestion/scheduler.py — verifies job registration only."""

from app.ingestion.scheduler import create_scheduler


def test_scheduler_has_three_jobs():
    scheduler = create_scheduler()
    assert len(scheduler.get_jobs()) == 3


def test_scheduler_has_garmin_poll_job():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "garmin_poll" in job_ids


def test_scheduler_has_garmin_backstop_job():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "garmin_backstop" in job_ids


def test_scheduler_has_strava_poll_job():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "strava_poll" in job_ids


def test_garmin_poll_runs_in_morning_hours():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "garmin_poll")
    trigger = job.trigger
    # CronTrigger fields: hour should cover 6–9
    hour_field = str(trigger.fields[trigger.FIELD_NAMES.index("hour")])
    assert "6" in hour_field or "6-9" in hour_field


def test_garmin_backstop_fires_at_10():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "garmin_backstop")
    trigger = job.trigger
    hour_field = str(trigger.fields[trigger.FIELD_NAMES.index("hour")])
    assert "10" in hour_field


def test_scheduler_not_running_after_create():
    """create_scheduler() should not auto-start the scheduler."""
    scheduler = create_scheduler()
    assert not scheduler.running
