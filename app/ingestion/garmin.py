"""Garmin Connect ingestion — overnight health metrics.

Pulls sleep score, sleep duration, HRV, resting HR, body battery, and stress
from Garmin Connect for the current day and stores them as MetricReading rows.

Idempotent — skips if today's Garmin data already exists in the database.
Stub mode (GARMIN_ENABLED=false) saves realistic mock readings without
contacting Garmin Connect.
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.config import get_settings
from app.core.redis_client import append_sync_log, cache_get, cache_set
from app.models.metric_reading import MetricReading, MetricSource, MetricType

logger = logging.getLogger(__name__)

_GARMIN_TOKEN_KEY = "garmin:session_token"
_GARMIN_TOKEN_TTL = 23 * 3600  # 23 hours — Garmin tokens valid for 24h


def _today_utc_morning() -> datetime:
    """Today's date at 06:00 UTC — used as the timestamp for overnight readings."""
    return datetime.now(timezone.utc).replace(
        hour=6, minute=0, second=0, microsecond=0
    )


def _has_today_data(db: Session) -> bool:
    """True if any Garmin reading already exists for today (UTC)."""
    start_of_day = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return (
        db.query(MetricReading)
        .filter(
            MetricReading.source == MetricSource.garmin,
            MetricReading.timestamp >= start_of_day,
        )
        .first()
    ) is not None


def _stub_reading_dicts() -> list[dict]:
    """Realistic mock readings for stub/test mode."""
    ts = _today_utc_morning()
    return [
        {"metric_type": MetricType.sleep_score,         "value": 78.0,  "timestamp": ts},
        {"metric_type": MetricType.sleep_duration_hours,"value": 7.5,   "timestamp": ts},
        {"metric_type": MetricType.hrv,                 "value": 65.0,  "timestamp": ts},
        {"metric_type": MetricType.resting_hr,          "value": 52.0,  "timestamp": ts},
        {"metric_type": MetricType.body_battery,        "value": 72.0,  "timestamp": ts},
        {"metric_type": MetricType.stress,              "value": 28.0,  "timestamp": ts},
    ]


def _persist(db: Session, reading_dicts: list[dict]) -> list[MetricReading]:
    """Insert reading dicts as MetricReading rows and return the saved objects.

    First attempts without explicit IDs so PostgreSQL's sequence provides them.
    Falls back to explicit IDs on IntegrityError — SQLite in the test environment
    has no sequence, so the id column would otherwise receive NULL.
    """
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    def _build(id_offset: Optional[int]) -> list[MetricReading]:
        max_id = 0
        if id_offset is not None:
            max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        rows = []
        for i, r in enumerate(reading_dicts):
            row = MetricReading(
                timestamp=r["timestamp"],
                metric_type=r["metric_type"],
                value=r.get("value"),
                text_value=r.get("text_value"),
                source=MetricSource.garmin,
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


# ── Session token caching ──────────────────────────────────────────────────────

def _login_with_token_cache(client) -> None:
    """Login to Garmin Connect, reusing a cached session token when available.

    garminconnect 0.3.x: pass a token string >512 chars to login(tokenstore=...)
    and the library calls self.client.loads() internally, skipping re-auth.
    On success the fresh token is serialised back to Redis.
    If cached login fails for any reason, falls back to full credential login.
    """
    cached = cache_get(_GARMIN_TOKEN_KEY)

    if cached:
        try:
            client.login(tokenstore=cached)
            logger.debug("Garmin: logged in via cached session token")
            # Refresh the TTL so tokens don't expire mid-session
            _store_token(client)
            return
        except Exception as exc:
            logger.warning(f"Garmin: cached token login failed ({exc}), falling back to credentials")

    # Full credential login — only reached on first run or after token expiry
    client.login()
    logger.info("Garmin: logged in with credentials")
    _store_token(client)


def _store_token(client) -> None:
    """Serialise the current Garmin session token to Redis."""
    try:
        token_str = client.client.dumps()
        cache_set(_GARMIN_TOKEN_KEY, token_str, _GARMIN_TOKEN_TTL)
        logger.debug("Garmin: session token cached in Redis")
    except Exception as exc:
        logger.warning(f"Garmin: could not cache session token: {exc}")


# ── Garmin API parsing ─────────────────────────────────────────────────────────

def _parse_garmin_readings(client, date_str: str) -> list[dict]:
    """Extract overnight metric dicts from Garmin API responses.

    Each sub-call is wrapped independently so a single failed endpoint
    doesn't prevent the others from being stored.
    """
    ts = _today_utc_morning()
    readings: list[dict] = []

    # Sleep score and duration
    try:
        sleep = client.get_sleep_data(date_str)
        dto = sleep.get("dailySleepDTO", {})
        score = dto.get("sleepScores", {}).get("overall", {}).get("value")
        duration_s = dto.get("sleepTimeSeconds")
        if score is not None:
            readings.append({"metric_type": MetricType.sleep_score,
                             "value": float(score), "timestamp": ts})
        if duration_s is not None:
            readings.append({"metric_type": MetricType.sleep_duration_hours,
                             "value": duration_s / 3600.0, "timestamp": ts})
    except Exception as exc:
        logger.warning(f"Garmin: sleep data unavailable: {exc}")

    # HRV
    try:
        hrv_data = client.get_hrv_data(date_str)
        last_night = hrv_data.get("hrvSummary", {}).get("lastNight")
        if last_night is not None:
            readings.append({"metric_type": MetricType.hrv,
                             "value": float(last_night), "timestamp": ts})
    except Exception as exc:
        logger.warning(f"Garmin: HRV data unavailable: {exc}")

    # Resting HR and average stress from daily stats
    try:
        stats = client.get_stats(date_str)
        rhr = stats.get("restingHeartRate")
        if rhr is not None:
            readings.append({"metric_type": MetricType.resting_hr,
                             "value": float(rhr), "timestamp": ts})
        avg_stress = stats.get("averageStressLevel")
        if avg_stress is not None and avg_stress > 0:
            readings.append({"metric_type": MetricType.stress,
                             "value": float(avg_stress), "timestamp": ts})
    except Exception as exc:
        logger.warning(f"Garmin: daily stats unavailable: {exc}")

    # Body battery — take the morning high-water mark
    try:
        bb_list = client.get_body_battery(date_str, date_str)
        if bb_list:
            max_bb = max((entry.get("charged", 0) for entry in bb_list), default=None)
            if max_bb:
                readings.append({"metric_type": MetricType.body_battery,
                                 "value": float(max_bb), "timestamp": ts})
    except Exception as exc:
        logger.warning(f"Garmin: body battery unavailable: {exc}")

    return readings


# ── Public entry point ─────────────────────────────────────────────────────────

def sync_garmin(db: Session) -> list[MetricReading]:
    """Pull overnight Garmin data and store as MetricReading rows.

    Returns the saved rows (empty list if skipped or on error).
    Safe to call repeatedly — idempotent.
    """
    ts = datetime.now(timezone.utc).isoformat()

    if _has_today_data(db):
        logger.info("Garmin: today's data already present — skipping")
        append_sync_log("garmin", {"ts": ts, "status": "skipped", "count": 0, "msg": "today's data already present"})
        return []

    settings = get_settings()

    if not settings.garmin_enabled:
        logger.info("Garmin: stub mode — saving mock readings")
        saved = _persist(db, _stub_reading_dicts())
        append_sync_log("garmin", {"ts": ts, "status": "ok", "count": len(saved), "msg": f"stub mode — {len(saved)} records"})
        return saved

    if not settings.garmin_email or not settings.garmin_password:
        logger.error("Garmin: GARMIN_EMAIL or GARMIN_PASSWORD not set — skipping")
        append_sync_log("garmin", {"ts": ts, "status": "error", "count": 0, "msg": "credentials not configured"})
        return []

    try:
        from garminconnect import Garmin  # type: ignore[import]
        client = Garmin(settings.garmin_email, settings.garmin_password)
        _login_with_token_cache(client)
        today_str = date.today().isoformat()
        reading_dicts = _parse_garmin_readings(client, today_str)
        saved = _persist(db, reading_dicts)
        logger.info(f"Garmin: saved {len(saved)} readings")
        append_sync_log("garmin", {"ts": ts, "status": "ok", "count": len(saved), "msg": f"{len(saved)} records saved"})
        return saved
    except Exception as exc:
        logger.error(f"Garmin sync failed: {exc}")
        append_sync_log("garmin", {"ts": ts, "status": "error", "count": 0, "msg": str(exc)[:120]})
        return []
