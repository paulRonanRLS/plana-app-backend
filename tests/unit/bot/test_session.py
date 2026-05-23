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
