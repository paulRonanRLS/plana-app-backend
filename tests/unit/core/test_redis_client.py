"""
Unit tests for Redis client.

Tests caching functionality with mocked Redis and stub mode.
"""

import pytest
from unittest.mock import Mock, patch

from app.core import redis_client


def test_get_redis_disabled_returns_none():
    """Test get_redis returns None when REDIS_ENABLED=false."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to disable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = False

    with patch('app.core.redis_client.get_settings', return_value=mock_settings):
        result = redis_client.get_redis()

        assert result is None


def test_get_redis_enabled_returns_client():
    """Test get_redis returns Redis client when REDIS_ENABLED=true."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to enable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = True
    mock_settings.redis_url = "redis://localhost:6379/0"

    # Mock Redis client
    mock_redis_instance = Mock()
    mock_redis_instance.ping.return_value = True

    with patch('app.core.redis_client.get_settings', return_value=mock_settings), \
         patch('app.core.redis_client.redis.from_url', return_value=mock_redis_instance):

        result = redis_client.get_redis()

        assert result is not None
        assert result == mock_redis_instance
        # Verify ping was called to test connection
        mock_redis_instance.ping.assert_called_once()


def test_cache_get_disabled_returns_none():
    """Test cache_get returns None when Redis is disabled."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to disable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = False

    with patch('app.core.redis_client.get_settings', return_value=mock_settings):
        result = redis_client.cache_get("test_key")

        assert result is None


def test_cache_get_returns_none_on_miss():
    """Test cache_get returns None when key doesn't exist."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to enable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = True
    mock_settings.redis_url = "redis://localhost:6379/0"

    # Mock Redis client with cache miss
    mock_redis_instance = Mock()
    mock_redis_instance.ping.return_value = True
    mock_redis_instance.get.return_value = None

    with patch('app.core.redis_client.get_settings', return_value=mock_settings), \
         patch('app.core.redis_client.redis.from_url', return_value=mock_redis_instance):

        result = redis_client.cache_get("nonexistent_key")

        assert result is None
        mock_redis_instance.get.assert_called_once_with("nonexistent_key")


def test_cache_get_returns_value_on_hit():
    """Test cache_get returns cached value when key exists."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to enable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = True
    mock_settings.redis_url = "redis://localhost:6379/0"

    # Mock Redis client with cache hit
    mock_redis_instance = Mock()
    mock_redis_instance.ping.return_value = True
    mock_redis_instance.get.return_value = "cached_value"

    with patch('app.core.redis_client.get_settings', return_value=mock_settings), \
         patch('app.core.redis_client.redis.from_url', return_value=mock_redis_instance):

        result = redis_client.cache_get("test_key")

        assert result == "cached_value"
        mock_redis_instance.get.assert_called_once_with("test_key")


def test_cache_get_handles_redis_exception():
    """Test cache_get returns None gracefully when Redis raises exception."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to enable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = True
    mock_settings.redis_url = "redis://localhost:6379/0"

    # Mock Redis client that raises exception on get
    mock_redis_instance = Mock()
    mock_redis_instance.ping.return_value = True
    mock_redis_instance.get.side_effect = Exception("Connection lost")

    with patch('app.core.redis_client.get_settings', return_value=mock_settings), \
         patch('app.core.redis_client.redis.from_url', return_value=mock_redis_instance):

        # Should not raise, should return None
        result = redis_client.cache_get("test_key")

        assert result is None


def test_cache_set_disabled_is_noop():
    """Test cache_set does nothing when Redis is disabled."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to disable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = False

    with patch('app.core.redis_client.get_settings', return_value=mock_settings):
        # Should not raise exception
        redis_client.cache_set("test_key", "test_value", 3600)


def test_cache_set_stores_value_with_ttl():
    """Test cache_set stores value with TTL when Redis is enabled."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to enable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = True
    mock_settings.redis_url = "redis://localhost:6379/0"

    # Mock Redis client
    mock_redis_instance = Mock()
    mock_redis_instance.ping.return_value = True

    with patch('app.core.redis_client.get_settings', return_value=mock_settings), \
         patch('app.core.redis_client.redis.from_url', return_value=mock_redis_instance):

        redis_client.cache_set("test_key", "test_value", 7200)

        # Verify setex was called with correct arguments
        mock_redis_instance.setex.assert_called_once_with("test_key", 7200, "test_value")


def test_cache_set_handles_redis_exception():
    """Test cache_set handles Redis exceptions gracefully."""
    # Reset module state
    redis_client._initialized = False
    redis_client._client = None

    # Mock settings to enable Redis
    mock_settings = Mock()
    mock_settings.redis_enabled = True
    mock_settings.redis_url = "redis://localhost:6379/0"

    # Mock Redis client that raises exception on setex
    mock_redis_instance = Mock()
    mock_redis_instance.ping.return_value = True
    mock_redis_instance.setex.side_effect = Exception("Connection lost")

    with patch('app.core.redis_client.get_settings', return_value=mock_settings), \
         patch('app.core.redis_client.redis.from_url', return_value=mock_redis_instance):

        # Should not raise exception
        redis_client.cache_set("test_key", "test_value", 3600)
