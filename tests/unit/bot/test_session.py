"""Unit tests for app/bot/session.py — all Redis calls mocked."""

import json
from unittest.mock import MagicMock

from app.bot import session as sess


def _mock_redis(stored: str | None = None) -> MagicMock:
    client = MagicMock()
    client.get.return_value = stored
    return client


# ── get_session ────────────────────────────────────────────────────────────────

def test_get_session_no_client():
    assert sess.get_session(None) == []


def test_get_session_empty_key():
    assert sess.get_session(_mock_redis(None)) == []


def test_get_session_returns_messages():
    messages = [{"role": "user", "content": "hello"}]
    client = _mock_redis(json.dumps(messages))
    assert sess.get_session(client) == messages


def test_get_session_handles_redis_error():
    client = MagicMock()
    client.get.side_effect = Exception("connection refused")
    assert sess.get_session(client) == []  # graceful fallback


# ── save_session ───────────────────────────────────────────────────────────────

def test_save_session_no_client():
    sess.save_session(None, [])  # no-op, no error


def test_save_session_calls_setex_with_ttl():
    client = _mock_redis()
    messages = [{"role": "user", "content": "hi"}]
    sess.save_session(client, messages)
    client.setex.assert_called_once_with(
        sess.SESSION_KEY, sess.SESSION_TTL, json.dumps(messages)
    )


def test_save_session_handles_redis_error():
    client = MagicMock()
    client.setex.side_effect = Exception("write failed")
    sess.save_session(client, [])  # no exception raised


# ── append_message ─────────────────────────────────────────────────────────────

def test_append_message_creates_first_entry():
    client = _mock_redis(None)
    result = sess.append_message(client, "user", "good morning")
    assert result == [{"role": "user", "content": "good morning"}]
    client.setex.assert_called_once()


def test_append_message_adds_to_existing():
    existing = [{"role": "user", "content": "first"}]
    client = _mock_redis(json.dumps(existing))
    result = sess.append_message(client, "assistant", "second")
    assert len(result) == 2
    assert result[-1] == {"role": "assistant", "content": "second"}


def test_append_message_preserves_order():
    client = _mock_redis(None)
    sess.append_message(client, "user", "A")
    # second call sees what was saved after the first
    client.get.return_value = json.dumps([{"role": "user", "content": "A"}])
    result = sess.append_message(client, "assistant", "B")
    assert result[0]["content"] == "A"
    assert result[1]["content"] == "B"


def test_append_message_no_client_returns_list():
    result = sess.append_message(None, "user", "hi")
    assert result == [{"role": "user", "content": "hi"}]


# ── clear_session ──────────────────────────────────────────────────────────────

def test_clear_session_deletes_key():
    client = _mock_redis()
    sess.clear_session(client)
    client.delete.assert_called_once_with(sess.SESSION_KEY)


def test_clear_session_no_client():
    sess.clear_session(None)  # no-op, no error


def test_clear_session_handles_redis_error():
    client = MagicMock()
    client.delete.side_effect = Exception("delete failed")
    sess.clear_session(client)  # no exception raised


# ── TTL constant ───────────────────────────────────────────────────────────────

def test_session_ttl_is_30_minutes():
    assert sess.SESSION_TTL == 1800


# ── pending capture ────────────────────────────────────────────────────────────

def test_set_pending_capture_stores_data():
    client = _mock_redis()
    sess.set_pending_capture(client, {"text": "cooked dinner", "confidence": 0.85})
    client.setex.assert_called_once()
    args = client.setex.call_args[0]
    assert args[0] == sess.PENDING_CAPTURE_KEY
    assert args[1] == sess.SESSION_TTL
    stored = json.loads(args[2])
    assert stored["text"] == "cooked dinner"
    assert stored["confidence"] == 0.85


def test_set_pending_capture_no_client():
    sess.set_pending_capture(None, {"text": "x"})  # no-op, no error


def test_set_pending_capture_handles_redis_error():
    client = MagicMock()
    client.setex.side_effect = Exception("write failed")
    sess.set_pending_capture(client, {"text": "x"})  # no exception raised


def test_get_pending_capture_returns_data():
    data = {"text": "cooked dinner", "confidence": 0.85}
    client = _mock_redis(json.dumps(data))
    result = sess.get_pending_capture(client)
    assert result == data


def test_get_pending_capture_none_when_empty():
    assert sess.get_pending_capture(_mock_redis(None)) is None


def test_get_pending_capture_no_client():
    assert sess.get_pending_capture(None) is None


def test_get_pending_capture_handles_redis_error():
    client = MagicMock()
    client.get.side_effect = Exception("connection refused")
    assert sess.get_pending_capture(client) is None


def test_clear_pending_capture_deletes_key():
    client = _mock_redis()
    sess.clear_pending_capture(client)
    client.delete.assert_called_once_with(sess.PENDING_CAPTURE_KEY)


def test_clear_pending_capture_no_client():
    sess.clear_pending_capture(None)  # no-op, no error


def test_clear_pending_capture_handles_redis_error():
    client = MagicMock()
    client.delete.side_effect = Exception("delete failed")
    sess.clear_pending_capture(client)  # no exception raised


def test_pending_capture_key_distinct_from_session_key():
    assert sess.PENDING_CAPTURE_KEY != sess.SESSION_KEY


# ── pending alert (drift / fade acknowledgement) ───────────────────────────────

def test_set_pending_alert_stores_data():
    client = _mock_redis()
    sess.set_pending_alert(client, {"goal_id": 42, "alert_type": "drift"})
    client.setex.assert_called_once()
    args = client.setex.call_args[0]
    assert args[0] == sess.PENDING_ALERT_KEY
    assert args[1] == sess.SESSION_TTL
    stored = json.loads(args[2])
    assert stored["goal_id"] == 42
    assert stored["alert_type"] == "drift"


def test_set_pending_alert_no_client():
    sess.set_pending_alert(None, {"goal_id": 1, "alert_type": "fade"})  # no-op, no error


def test_set_pending_alert_handles_redis_error():
    client = MagicMock()
    client.setex.side_effect = Exception("write failed")
    sess.set_pending_alert(client, {"goal_id": 1, "alert_type": "drift"})  # no exception raised


def test_get_pending_alert_returns_data():
    data = {"goal_id": 7, "alert_type": "fade"}
    client = _mock_redis(json.dumps(data))
    result = sess.get_pending_alert(client)
    assert result == data


def test_get_pending_alert_none_when_empty():
    assert sess.get_pending_alert(_mock_redis(None)) is None


def test_get_pending_alert_no_client():
    assert sess.get_pending_alert(None) is None


def test_get_pending_alert_handles_redis_error():
    client = MagicMock()
    client.get.side_effect = Exception("connection refused")
    assert sess.get_pending_alert(client) is None


def test_clear_pending_alert_deletes_key():
    client = _mock_redis()
    sess.clear_pending_alert(client)
    client.delete.assert_called_once_with(sess.PENDING_ALERT_KEY)


def test_clear_pending_alert_no_client():
    sess.clear_pending_alert(None)  # no-op, no error


def test_clear_pending_alert_handles_redis_error():
    client = MagicMock()
    client.delete.side_effect = Exception("delete failed")
    sess.clear_pending_alert(client)  # no exception raised


def test_pending_alert_key_distinct_from_session_key():
    assert sess.PENDING_ALERT_KEY != sess.SESSION_KEY


def test_pending_alert_key_distinct_from_capture_key():
    assert sess.PENDING_ALERT_KEY != sess.PENDING_CAPTURE_KEY
