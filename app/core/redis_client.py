"""
Redis caching client for URL extraction results.

Provides a simple key-value cache with TTL support. When REDIS_ENABLED=false,
all operations are no-ops (cache always misses, nothing is stored).
"""

import logging
import redis
from app.config import get_settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None
_initialized = False


def get_redis() -> redis.Redis | None:
    """
    Get the configured Redis client instance.

    Returns None if REDIS_ENABLED=false, allowing graceful degradation.
    Otherwise returns a configured client ready for caching operations.

    Returns:
        redis.Redis | None: Configured client or None if disabled
    """
    global _client, _initialized

    if _initialized:
        return _client

    settings = get_settings()

    # Check if Redis is enabled
    redis_enabled = getattr(settings, 'redis_enabled', True)

    if not redis_enabled:
        logger.info("Redis is disabled (REDIS_ENABLED=false) - caching will be skipped")
        _client = None
        _initialized = True
        return _client

    # Initialize Redis client
    try:
        redis_url = getattr(settings, 'redis_url', 'redis://localhost:6379')
        _client = redis.from_url(redis_url, decode_responses=True)

        # Test connection
        _client.ping()
        logger.info(f"Redis connected: {redis_url}")

    except Exception as e:
        logger.warning(f"Failed to connect to Redis: {e} - continuing without cache")
        _client = None

    _initialized = True
    return _client


def cache_get(key: str) -> str | None:
    """
    Get a value from the Redis cache.

    Args:
        key: Cache key

    Returns:
        str | None: Cached value or None if not found/disabled
    """
    client = get_redis()

    if client is None:
        return None

    try:
        return client.get(key)
    except Exception as e:
        logger.warning(f"Redis GET failed for key {key}: {e}")
        return None


def cache_set(key: str, value: str, ttl_seconds: int) -> None:
    """
    Set a value in the Redis cache with TTL.

    Args:
        key: Cache key
        value: Value to cache
        ttl_seconds: Time to live in seconds
    """
    client = get_redis()

    if client is None:
        return

    try:
        client.setex(key, ttl_seconds, value)
    except Exception as e:
        logger.warning(f"Redis SET failed for key {key}: {e}")
