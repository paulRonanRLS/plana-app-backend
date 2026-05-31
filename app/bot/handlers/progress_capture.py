"""Handler for progress_capture intent."""

import logging

from app.bot.handlers.base import HandlerContext, IntentHandler
from app.bot.handlers.registry import REGISTRY
from app.bot import session as session_mgr
from app.services import capture as capture_service

logger = logging.getLogger(__name__)


class ProgressCaptureHandler(IntentHandler):
    intent = "progress_capture"

    async def handle(self, ctx: HandlerContext) -> str:
        matched = (
            capture_service.match_goal_by_keywords(ctx.text, ctx.active_goals)
            or capture_service.match_goal_title(ctx.text, ctx.active_goals)
        )
        if matched:
            capture_service.record_progress(ctx.db, ctx.text, goal_id=matched.id)
            logger.debug(f"Direct capture: goal={matched.title}")
            return f"Logged for {matched.title}."

        session_mgr.set_pending_capture(
            ctx.redis_client, {"text": ctx.text, "confidence": ctx.confidence}
        )
        if ctx.confidence > 0.8:
            return "Got it. Which goal was that for?"
        return "Which goal was that for?"

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(ProgressCaptureHandler())
