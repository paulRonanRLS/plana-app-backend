"""Intent handler registry — importing this package registers all 11 handlers."""

from app.bot.handlers.registry import REGISTRY  # noqa: F401

# Each import triggers module-level REGISTRY.register(...) calls.
import app.bot.handlers.activity_query  # noqa: F401
import app.bot.handlers.free_response  # noqa: F401
import app.bot.handlers.goal_query  # noqa: F401
import app.bot.handlers.goal_state_change  # noqa: F401
import app.bot.handlers.illness_log  # noqa: F401
import app.bot.handlers.metric_log  # noqa: F401
import app.bot.handlers.milestone_complete  # noqa: F401
import app.bot.handlers.morning_checkin  # noqa: F401
import app.bot.handlers.physical_state  # noqa: F401
import app.bot.handlers.progress_capture  # noqa: F401
import app.bot.handlers.sacrifice_log  # noqa: F401

__all__ = ["REGISTRY"]
