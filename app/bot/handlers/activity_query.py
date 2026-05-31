"""Handler for activity_query intent."""

import asyncio
import logging

from app.bot.handlers.base import HandlerContext, IntentHandler
from app.bot.handlers.registry import REGISTRY
from app.intelligence import activity_query as activity_query_module
from app.services.activity import _parse_activity_type, parse_date_reference, query_activities

logger = logging.getLogger(__name__)


class ActivityQueryHandler(IntentHandler):
    intent = "activity_query"

    async def handle(self, ctx: HandlerContext) -> str:
        if ctx.claude_client is None:
            return "Activity lookup requires Claude enabled."
        start, end = parse_date_reference(ctx.text)
        activity_type = _parse_activity_type(ctx.text)
        logger.debug(
            f"activity_query: type={activity_type!r} range={start.date()}–{end.date()}"
        )
        activities = await asyncio.to_thread(
            query_activities, ctx.db, start, end, activity_type
        )
        logger.debug(f"activity_query: found {len(activities)} activities")
        return await asyncio.to_thread(
            activity_query_module.build_response, ctx.text, activities, ctx.claude_client
        )


REGISTRY.register(ActivityQueryHandler())
