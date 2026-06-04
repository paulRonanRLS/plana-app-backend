"""Handler for free_response intent."""

import logging

from app.bot.handlers.base import HandlerContext, IntentHandler, build_goals_system_prompt, claude_response
from app.bot.handlers.registry import REGISTRY
from app.bot import session as session_mgr
from app.services import capture as capture_service

logger = logging.getLogger(__name__)


class FreeResponseHandler(IntentHandler):
    intent = "free_response"

    async def handle(self, ctx: HandlerContext) -> str:
        if ctx.pending_capture:
            # Fix 3: try keyword match before title match for pending capture resolution.
            matched = (
                capture_service.match_goal_by_keywords(ctx.text, ctx.active_goals)
                or capture_service.match_goal_title(ctx.text, ctx.active_goals)
            )
            if matched:
                capture_service.record_progress(
                    ctx.db, ctx.pending_capture["text"], goal_id=matched.id
                )
                session_mgr.clear_pending_capture(ctx.redis_client)
                logger.debug(f"Pending capture resolved: goal={matched.title}")
                return f"Logged for {matched.title}."
            session_mgr.clear_pending_capture(ctx.redis_client)
            logger.debug("Pending capture unresolved — dropping, treating as free_response")

        if ctx.claude_client is None:
            return "Tell me more."
        system_prompt = build_goals_system_prompt(ctx.goals, ctx.db)
        return await claude_response(ctx.messages, system_prompt, ctx.claude_client)

    def uses_pending_capture(self) -> bool:
        return True


REGISTRY.register(FreeResponseHandler())
