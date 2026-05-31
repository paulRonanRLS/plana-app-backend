"""Handler for goal_query intent."""

import asyncio
import logging

from app.bot.handlers.base import HandlerContext, IntentHandler
from app.bot.handlers.registry import REGISTRY
from app.intelligence import goal_query as goal_query_module

logger = logging.getLogger(__name__)


class GoalQueryHandler(IntentHandler):
    intent = "goal_query"

    async def handle(self, ctx: HandlerContext) -> str:
        if ctx.claude_client is None:
            return "Ask me again with Claude enabled for real goal analysis."
        return await asyncio.to_thread(
            goal_query_module.build_response,
            ctx.text, ctx.goals, ctx.db, ctx.claude_client,
        )


REGISTRY.register(GoalQueryHandler())
