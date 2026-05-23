"""Activity query service — date parsing and DB retrieval for past activities."""

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.metric_reading import MetricReading, MetricSource, MetricType

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_ACTIVITY_TYPE_KEYWORDS = {
    "run": ("run", "running", "ran", "jog", "jogging"),
    "ride": ("ride", "riding", "rode", "cycle", "cycling", "cycled", "bike"),
    "swim": ("swim", "swimming", "swam"),
    "walk": ("walk", "walking", "walked", "hike", "hiking", "hiked"),
}


def parse_date_reference(text: str, today: Optional[datetime] = None) -> tuple[datetime, datetime]:
    """Parse a natural language date reference into a (start, end) UTC range.

    Handles:
      - "yesterday", "today"
      - Weekday names: "Sunday", "last Monday", etc.
      - "last week"
      - ISO dates: "2026-05-20"

    Returns (start_of_day_utc, end_of_day_utc). For "last week" returns the
    full Mon–Sun range of the previous calendar week.
    Defaults to yesterday if no temporal reference is found.
    """
    if today is None:
        today = datetime.now(timezone.utc)
    today_date = today.date()
    low = text.lower()

    # ISO date: YYYY-MM-DD
    iso_match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_match:
        try:
            d = datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
            return _day_range(d)
        except ValueError:
            pass

    # "last week"
    if "last week" in low:
        # Previous Monday–Sunday
        days_since_monday = today_date.weekday()
        last_monday = today_date - timedelta(days=days_since_monday + 7)
        last_sunday = last_monday + timedelta(days=6)
        start = datetime.combine(last_monday, datetime.min.time(), tzinfo=timezone.utc)
        end = datetime.combine(last_sunday, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
        return start, end

    # "today"
    if "today" in low:
        return _day_range(today_date)

    # "yesterday"
    if "yesterday" in low:
        return _day_range(today_date - timedelta(days=1))

    # Weekday names — "last Sunday", "on Saturday", or bare weekday
    for name, weekday_num in _WEEKDAYS.items():
        if name in low:
            days_since_monday = today_date.weekday()
            this_week_day = today_date - timedelta(days=days_since_monday) + timedelta(days=weekday_num)
            # If that day is in the future or is today, go back one week
            if this_week_day >= today_date:
                this_week_day -= timedelta(days=7)
            return _day_range(this_week_day)

    # Default: yesterday
    return _day_range(today_date - timedelta(days=1))


def _day_range(date) -> tuple[datetime, datetime]:
    start = datetime.combine(date, datetime.min.time(), tzinfo=timezone.utc)
    end = datetime.combine(date, datetime.max.time().replace(microsecond=0), tzinfo=timezone.utc)
    return start, end


def _parse_activity_type(text: str) -> Optional[str]:
    """Extract activity type keyword from text, or None for any."""
    low = text.lower()
    for activity_type, keywords in _ACTIVITY_TYPE_KEYWORDS.items():
        if any(k in low for k in keywords):
            return activity_type
    return None


def query_activities(
    db: Session,
    start: datetime,
    end: datetime,
    activity_type: Optional[str] = None,
) -> list[dict]:
    """Return activity MetricReadings in the given UTC range, parsed from JSON notes.

    Each returned dict has at minimum:
      timestamp, source, name, sport_type, distance_m, moving_time_s, elapsed_time_s
    Plus optional: tss, normalized_power_w, average_hr, max_hr, strava_id
    """
    q = db.query(MetricReading).filter(
        MetricReading.metric_type == MetricType.activity,
        MetricReading.timestamp >= start,
        MetricReading.timestamp <= end,
    ).order_by(MetricReading.timestamp.desc())

    rows = q.all()
    results = []
    for row in rows:
        try:
            notes = json.loads(row.notes) if row.notes else {}
        except (ValueError, TypeError):
            notes = {}

        activity = {
            "timestamp": row.timestamp,
            "source": row.source.value if row.source else None,
            **notes,
        }
        # normalise sport type — strava stores it as "type", garmin as "sport_type"
        if "sport_type" not in activity and "type" in activity:
            activity["sport_type"] = activity["type"]
        # normalise distance — strava stores distance_km; convert to distance_m
        if "distance_m" not in activity and "distance_km" in activity:
            dk = activity["distance_km"]
            activity["distance_m"] = dk * 1000 if dk is not None else None
        # normalise hr field names — strava stores avg_hr; use average_hr
        if "average_hr" not in activity and "avg_hr" in activity:
            activity["average_hr"] = activity["avg_hr"]
        if "max_hr" not in activity and "max_hr" in activity:
            pass  # already correct key

        if activity_type and activity_type != "any":
            sport = activity.get("sport_type", "").lower()
            if activity_type not in sport and sport not in activity_type:
                continue

        results.append(activity)

    return results
