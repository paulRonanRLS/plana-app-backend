"""Handler for illness_log intent."""

import logging

from app.bot.handlers.base import HandlerContext, IntentHandler, build_goals_system_prompt, claude_response, write_capture
from app.bot.handlers.registry import REGISTRY

logger = logging.getLogger(__name__)


class IllnessLogHandler(IntentHandler):
    intent = "illness_log"

    async def handle(self, ctx: HandlerContext) -> str:
        write_capture(ctx.db, "illness_log", ctx.text)
        if ctx.claude_client is None:
            return "Got it. How long have you been feeling this way?"
        system_prompt = build_goals_system_prompt(ctx.goals)
        return await claude_response(ctx.messages, system_prompt, ctx.claude_client)

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(IllnessLogHandler())
