"""Handler for metric_log intent."""

import logging

from app.bot.handlers.base import HandlerContext, IntentHandler, build_goals_system_prompt, claude_response, write_capture
from app.bot.handlers.registry import REGISTRY

logger = logging.getLogger(__name__)


class MetricLogHandler(IntentHandler):
    intent = "metric_log"

    async def handle(self, ctx: HandlerContext) -> str:
        write_capture(ctx.db, "metric_log", ctx.text)
        if ctx.claude_client is None:
            return "Logged."
        system_prompt = build_goals_system_prompt(ctx.goals, ctx.db)
        return await claude_response(ctx.messages, system_prompt, ctx.claude_client)

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(MetricLogHandler())
