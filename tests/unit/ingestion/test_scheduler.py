"""Unit tests for app/ingestion/scheduler.py — verifies job registration only."""

from app.ingestion.scheduler import create_scheduler


def test_scheduler_has_five_jobs():
    scheduler = create_scheduler()
    assert len(scheduler.get_jobs()) == 5


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


def test_scheduler_has_drift_check_job():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "drift_check" in job_ids


def test_scheduler_has_fade_check_job():
    scheduler = create_scheduler()
    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "fade_check" in job_ids


def test_garmin_poll_runs_in_morning_hours():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "garmin_poll")
    trigger = job.trigger
    hour_field = str(trigger.fields[trigger.FIELD_NAMES.index("hour")])
    assert "6" in hour_field or "6-9" in hour_field


def test_garmin_backstop_fires_at_10():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "garmin_backstop")
    trigger = job.trigger
    hour_field = str(trigger.fields[trigger.FIELD_NAMES.index("hour")])
    assert "10" in hour_field


def test_garmin_poll_is_hourly_not_quarter_hourly():
    """Verify reduced poll rate — once per hour, not every 15 minutes."""
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "garmin_poll")
    minute_field = str(job.trigger.fields[job.trigger.FIELD_NAMES.index("minute")])
    assert minute_field == "0"


def test_drift_check_fires_at_0830():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "drift_check")
    trigger = job.trigger
    hour_field = str(trigger.fields[trigger.FIELD_NAMES.index("hour")])
    minute_field = str(trigger.fields[trigger.FIELD_NAMES.index("minute")])
    assert "8" in hour_field
    assert "30" in minute_field


def test_fade_check_fires_on_monday():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "fade_check")
    trigger = job.trigger
    dow_field = str(trigger.fields[trigger.FIELD_NAMES.index("day_of_week")])
    assert "mon" in dow_field.lower() or "0" in dow_field


def test_fade_check_fires_at_0900():
    scheduler = create_scheduler()
    job = next(j for j in scheduler.get_jobs() if j.id == "fade_check")
    trigger = job.trigger
    hour_field = str(trigger.fields[trigger.FIELD_NAMES.index("hour")])
    minute_field = str(trigger.fields[trigger.FIELD_NAMES.index("minute")])
    assert "9" in hour_field
    assert "0" in minute_field


def test_scheduler_not_running_after_create():
    """create_scheduler() should not auto-start the scheduler."""
    scheduler = create_scheduler()
    assert not scheduler.running
