"""Strava ingestion — recent activities.

Pulls recent activities from the Strava API using the OAuth2 refresh token
flow, calculates TSS for cycling activities with power data, and stores
each activity as a MetricReading row (metric_type=activity).

A separate tss MetricReading is also created for cycling activities where
TSS can be calculated, so it feeds into the resource service TSS baseline.

Idempotent — the Strava activity ID is stored in the notes JSON and checked
before inserting to prevent duplicates.

Stub mode (STRAVA_ENABLED=false) saves a realistic mock activity without
contacting Strava.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.redis_client import append_sync_log
from app.models.metric_reading import MetricReading, MetricSource, MetricType

logger = logging.getLogger(__name__)

STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"

# Default FTP used for TSS calculation when no profile value is available.
# TSS = (moving_time_s * NP * IF) / (FTP * 3600) * 100
# where IF = NP / FTP, so TSS = moving_time_s * NP^2 / (FTP^2 * 36)
DEFAULT_FTP_WATTS = 250


def _calculate_tss(moving_time_s: int, normalized_power_w: float, ftp_w: float) -> float:
    """Calculate Training Stress Score from power data."""
    intensity_factor = normalized_power_w / ftp_w
    return (moving_time_s * normalized_power_w * intensity_factor) / (ftp_w * 3600) * 100


def _activity_already_stored(db: Session, strava_id: int) -> bool:
    """True if an activity with this Strava ID is already in the database."""
    return (
        db.query(MetricReading)
        .filter(
            MetricReading.source == MetricSource.strava,
            MetricReading.metric_type == MetricType.activity,
            MetricReading.notes.contains(f'"strava_id": {strava_id}'),
        )
        .first()
    ) is not None


def _stub_activity_dicts() -> list[dict]:
    """Realistic mock activity data for stub/test mode."""
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    return [
        {
            "strava_id": 999000001,
            "timestamp": yesterday.replace(hour=7, minute=0, second=0, microsecond=0),
            "activity_type": "Run",
            "distance_km": 10.2,
            "moving_time_s": 3180,
            "elapsed_time_s": 3240,
            "avg_hr": 148,
            "max_hr": 165,
            "normalized_power_w": None,
            "tss": None,
        }
    ]


def _activity_to_rows(activity: dict) -> list[dict]:
    """Convert a parsed activity dict to one or two MetricReading dicts.

    Always produces an 'activity' row.
    Also produces a 'tss' row if TSS was calculated (feeds resource service).
    """
    notes = json.dumps({
        "strava_id": activity["strava_id"],
        "name": activity.get("name", ""),
        "type": activity["activity_type"],
        "distance_km": activity.get("distance_km"),
        "moving_time_s": activity.get("moving_time_s"),
        "elapsed_time_s": activity.get("elapsed_time_s"),
        "avg_hr": activity.get("avg_hr"),
        "max_hr": activity.get("max_hr"),
        "normalized_power_w": activity.get("normalized_power_w"),
        "tss": activity.get("tss"),
    })
    rows = [
        {
            "timestamp": activity["timestamp"],
            "metric_type": MetricType.activity,
            "value": activity.get("distance_km"),
            "text_value": activity["activity_type"],
            "notes": notes,
            "source": MetricSource.strava,
        }
    ]
    if activity.get("tss") is not None:
        rows.append({
            "timestamp": activity["timestamp"],
            "metric_type": MetricType.tss,
            "value": activity["tss"],
            "source": MetricSource.strava,
        })
    return rows


def _persist(db: Session, row_dicts: list[dict]) -> list[MetricReading]:
    """Insert MetricReading rows and return the saved objects.

    First attempts without explicit IDs so PostgreSQL's sequence provides them.
    Falls back to explicit IDs on IntegrityError — SQLite (test env) has no
    sequence so the id column would otherwise receive NULL.
    """
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    def _build(id_offset: Optional[int]) -> list[MetricReading]:
        max_id = 0
        if id_offset is not None:
            max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        rows = []
        for i, r in enumerate(row_dicts):
            row = MetricReading(
                timestamp=r["timestamp"],
                metric_type=r["metric_type"],
                value=r.get("value"),
                text_value=r.get("text_value"),
                source=r.get("source", MetricSource.strava),
                notes=r.get("notes"),
            )
            if id_offset is not None:
                row.id = max_id + i + 1
            db.add(row)
            rows.append(row)
        return rows

    rows = _build(id_offset=None)
    try:
        db.commit()
        return rows
    except IntegrityError:
        db.rollback()
        rows = _build(id_offset=0)  # triggers max_id lookup
        db.commit()
        return rows


def _get_access_token(settings) -> Optional[str]:
    """Exchange refresh token for a fresh access token."""
    resp = requests.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": settings.strava_client_id,
            "client_secret": settings.strava_client_secret,
            "refresh_token": settings.strava_refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("access_token")


def _parse_activity(raw: dict) -> dict:
    """Parse a raw Strava activity response into a canonical dict."""
    ts_str = raw.get("start_date") or raw.get("start_date_local", "")
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        ts = datetime.now(timezone.utc)

    moving_time_s = raw.get("moving_time", 0)
    np_w = raw.get("weighted_average_watts") if raw.get("device_watts") else None
    tss = None
    if np_w and moving_time_s:
        tss = round(_calculate_tss(moving_time_s, float(np_w), DEFAULT_FTP_WATTS), 1)

    return {
        "strava_id": raw["id"],
        "name": raw.get("name", ""),
        "timestamp": ts,
        "activity_type": raw.get("sport_type") or raw.get("type", "Unknown"),
        "distance_km": round(raw.get("distance", 0) / 1000, 2),
        "moving_time_s": moving_time_s,
        "elapsed_time_s": raw.get("elapsed_time"),
        "avg_hr": raw.get("average_heartrate"),
        "max_hr": raw.get("max_heartrate"),
        "normalized_power_w": np_w,
        "tss": tss,
    }


# ── Public entry point ─────────────────────────────────────────────────────────

def sync_strava(db: Session, days_back: int = 7) -> list[MetricReading]:
    """Pull recent Strava activities and store as MetricReading rows.

    Returns the saved rows (empty list if nothing new or on error).
    Safe to call repeatedly — idempotent per activity ID.
    """
    ts = datetime.now(timezone.utc).isoformat()
    settings = get_settings()

    if not settings.strava_enabled:
        logger.info("Strava: stub mode — saving mock activity")
        saved = []
        for activity in _stub_activity_dicts():
            if _activity_already_stored(db, activity["strava_id"]):
                logger.info(f"Strava: activity {activity['strava_id']} already stored — skipping")
                continue
            rows = _activity_to_rows(activity)
            saved.extend(_persist(db, rows))
        append_sync_log("strava", {"ts": ts, "status": "ok", "count": len(saved), "msg": f"stub mode — {len(saved)} records"})
        return saved

    required = [settings.strava_client_id, settings.strava_client_secret,
                settings.strava_refresh_token]
    if not all(required):
        logger.error("Strava: credentials not fully configured — skipping")
        append_sync_log("strava", {"ts": ts, "status": "error", "count": 0, "msg": "credentials not configured"})
        return []

    try:
        access_token = _get_access_token(settings)
        since = datetime.now(timezone.utc) - timedelta(days=days_back)
        params = {
            "after": int(since.timestamp()),
            "per_page": 50,
        }
        resp = requests.get(
            STRAVA_ACTIVITIES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=15,
        )
        resp.raise_for_status()
        activities_raw = resp.json()
    except Exception as exc:
        logger.error(f"Strava: API request failed: {exc}")
        append_sync_log("strava", {"ts": ts, "status": "error", "count": 0, "msg": str(exc)[:120]})
        return []

    saved = []
    for raw in activities_raw:
        try:
            activity = _parse_activity(raw)
            if _activity_already_stored(db, activity["strava_id"]):
                logger.debug(f"Strava: activity {activity['strava_id']} already stored — skipping")
                continue
            rows = _activity_to_rows(activity)
            new_rows = _persist(db, rows)
            saved.extend(new_rows)
            logger.info(
                f"Strava: stored {activity['activity_type']} "
                f"{activity['distance_km']}km id={activity['strava_id']}"
            )
        except Exception as exc:
            logger.error(f"Strava: failed to process activity {raw.get('id')}: {exc}")

    append_sync_log("strava", {"ts": ts, "status": "ok", "count": len(saved), "msg": f"{len(saved)} records saved"})
    return saved
