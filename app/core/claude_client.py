"""
Anthropic Claude API client initialization and management.

Provides a configured client instance that respects CLAUDE_ENABLED flag.
When disabled (e.g., in tests), returns None to allow stub behavior.
"""

import anthropic
from app.config import get_settings

_client: anthropic.Anthropic | None = None
_initialized = False


def get_client() -> anthropic.Anthropic | None:
    """
    Get the configured Anthropic client instance.

    Returns None if CLAUDE_ENABLED=false, allowing services to use mock data.
    Otherwise returns a configured client ready to make API calls.

    Returns:
        anthropic.Anthropic | None: Configured client or None if disabled
    """
    global _client, _initialized

    if _initialized:
        return _client

    settings = get_settings()

    # If Claude is disabled, return None (for tests and stub mode)
    if not settings.claude_enabled:
        _client = None
        _initialized = True
        return _client

    # If Claude is enabled but no API key, raise clear error
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "CLAUDE_ENABLED=true but ANTHROPIC_API_KEY is not set. "
            "Either provide an API key or set CLAUDE_ENABLED=false for stub mode."
        )

    # Initialize the client
    _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    _initialized = True

    return _client
