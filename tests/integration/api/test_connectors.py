"""API integration tests for GET /v1/connectors/status."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.models.metric_reading import MetricReading, MetricSource, MetricType


def _add_reading(db, source: MetricSource, metric_type: MetricType = MetricType.hrv):
    _add_reading._id_counter = getattr(_add_reading, "_id_counter", 0) + 1
    r = MetricReading(
        id=_add_reading._id_counter,
        timestamp=datetime.now(timezone.utc),
        metric_type=metric_type,
        value=60.0,
        source=source,
    )
    db.add(r)
    db.commit()
    return r


# ── GET /v1/connectors/status ──────────────────────────────────────────────────

def test_connectors_status_shape(test_app):
    resp = test_app.get("/v1/connectors/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "garmin" in data
    assert "strava" in data
    assert "record_counts" in data


def test_connectors_status_garmin_fields(test_app):
    data = test_app.get("/v1/connectors/status").json()
    g = data["garmin"]
    assert "enabled" in g
    assert "status" in g
    assert "last_sync" in g
    assert "record_count" in g
    assert "log" in g


def test_connectors_status_strava_fields(test_app):
    data = test_app.get("/v1/connectors/status").json()
    s = data["strava"]
    assert "enabled" in s
    assert "status" in s
    assert "last_sync" in s
    assert "record_count" in s
    assert "log" in s


def test_connectors_status_record_counts_keys(test_app):
    counts = test_app.get("/v1/connectors/status").json()["record_counts"]
    assert "garmin" in counts
    assert "strava" in counts
    assert "manual" in counts
    assert "telegram" in counts


def test_connectors_status_no_redis_no_last_sync(test_app):
    with patch("app.core.redis_client.cache_get", return_value=None):
        data = test_app.get("/v1/connectors/status").json()
    assert data["garmin"]["last_sync"] is None
    assert data["garmin"]["status"] == "never"


def test_connectors_status_recent_sync_is_green(test_app):
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with patch("app.core.redis_client.cache_get", return_value=recent):
        data = test_app.get("/v1/connectors/status").json()
    assert data["garmin"]["status"] == "green"


def test_connectors_status_stale_sync_is_amber(test_app):
    stale = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    with patch("app.core.redis_client.cache_get", return_value=stale):
        data = test_app.get("/v1/connectors/status").json()
    assert data["garmin"]["status"] == "amber"


def test_connectors_status_old_sync_is_red(test_app):
    old = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    with patch("app.core.redis_client.cache_get", return_value=old):
        data = test_app.get("/v1/connectors/status").json()
    assert data["garmin"]["status"] == "red"


def test_connectors_status_garmin_record_count(test_app, test_db):
    _add_reading(test_db, MetricSource.garmin)
    _add_reading(test_db, MetricSource.garmin)
    data = test_app.get("/v1/connectors/status").json()
    assert data["garmin"]["record_count"] == 2
    assert data["record_counts"]["garmin"] == 2


def test_connectors_status_strava_record_count(test_app, test_db):
    _add_reading(test_db, MetricSource.strava, MetricType.activity)
    data = test_app.get("/v1/connectors/status").json()
    assert data["strava"]["record_count"] == 1
    assert data["record_counts"]["strava"] == 1


def test_connectors_status_telegram_record_count(test_app, test_db):
    _add_reading(test_db, MetricSource.telegram, MetricType.habit_log)
    data = test_app.get("/v1/connectors/status").json()
    assert data["record_counts"]["telegram"] == 1


def test_connectors_status_log_is_list(test_app):
    with patch("app.core.redis_client.get_sync_log", return_value=[]):
        data = test_app.get("/v1/connectors/status").json()
    assert isinstance(data["garmin"]["log"], list)
    assert isinstance(data["strava"]["log"], list)


def test_connectors_status_log_entries_returned(test_app):
    fake_log = [{"ts": "2026-05-26T07:00:00+00:00", "status": "ok", "count": 6, "msg": "stub mode"}]
    with patch("app.core.redis_client.get_sync_log", return_value=fake_log):
        data = test_app.get("/v1/connectors/status").json()
    assert data["garmin"]["log"] == fake_log


# ── Redis sync log helpers ─────────────────────────────────────────────────────

def test_append_sync_log_no_redis_no_error():
    from app.core.redis_client import append_sync_log
    with patch("app.core.redis_client.get_redis", return_value=None):
        append_sync_log("garmin", {"ts": "x", "status": "ok", "count": 1, "msg": "test"})


def test_get_sync_log_no_redis_returns_empty():
    from app.core.redis_client import get_sync_log
    with patch("app.core.redis_client.get_redis", return_value=None):
        assert get_sync_log("garmin") == []


def test_append_sync_log_redis_error_no_exception():
    from unittest.mock import MagicMock
    from app.core.redis_client import append_sync_log
    client = MagicMock()
    client.lpush.side_effect = Exception("connection refused")
    with patch("app.core.redis_client.get_redis", return_value=client):
        append_sync_log("garmin", {"ts": "x", "status": "ok", "count": 0, "msg": ""})


def test_get_sync_log_redis_error_returns_empty():
    from unittest.mock import MagicMock
    from app.core.redis_client import get_sync_log
    client = MagicMock()
    client.lrange.side_effect = Exception("connection refused")
    with patch("app.core.redis_client.get_redis", return_value=client):
        assert get_sync_log("strava") == []


def test_append_sync_log_calls_lpush_ltrim_expire():
    import json
    from unittest.mock import MagicMock, call
    from app.core.redis_client import append_sync_log, _SYNC_LOG_MAX, _SYNC_LOG_TTL
    client = MagicMock()
    entry = {"ts": "2026-05-26T07:00:00+00:00", "status": "ok", "count": 6, "msg": "stub"}
    with patch("app.core.redis_client.get_redis", return_value=client):
        append_sync_log("garmin", entry)
    client.lpush.assert_called_once_with("sync:garmin:log", json.dumps(entry))
    client.ltrim.assert_called_once_with("sync:garmin:log", 0, _SYNC_LOG_MAX - 1)
    client.expire.assert_called_once_with("sync:garmin:log", _SYNC_LOG_TTL)


def test_get_sync_log_parses_json():
    import json
    from unittest.mock import MagicMock
    from app.core.redis_client import get_sync_log
    entry = {"ts": "2026-05-26T07:00:00+00:00", "status": "ok", "count": 6, "msg": "test"}
    client = MagicMock()
    client.lrange.return_value = [json.dumps(entry)]
    with patch("app.core.redis_client.get_redis", return_value=client):
        result = get_sync_log("garmin")
    assert result == [entry]
