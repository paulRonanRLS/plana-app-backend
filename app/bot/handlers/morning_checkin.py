"""Handler for morning_checkin intent."""

import asyncio
import logging

from app.bot.handlers.base import HandlerContext, IntentHandler, build_goals_system_prompt, claude_response, write_capture
from app.bot.handlers.registry import REGISTRY
from app.intelligence import checkin as checkin_module
from app.services.resource import get_resource_tension

logger = logging.getLogger(__name__)

_STUB = (
    "Good morning. How are you feeling today — physically and mentally? "
    "Good, neutral, or flat?"
)


class MorningCheckinHandler(IntentHandler):
    intent = "morning_checkin"

    async def handle(self, ctx: HandlerContext) -> str:
        # Fix 1: persist the original pre-10am capture (physical/illness/metric)
        # even though intent was overridden to morning_checkin.
        write_capture(ctx.db, ctx.original_intent, ctx.text)

        if ctx.claude_client is None:
            return _STUB

        tension = get_resource_tension(ctx.db)
        return await asyncio.to_thread(
            checkin_module.build_response,
            ctx.messages,
            ctx.goals,
            ctx.claude_client,
            time_envelope_hours=tension.time_envelope_hours,
            recovery_envelope_tss=tension.recovery_envelope_tss,
            time_ratio=tension.time_ratio,
            recovery_ratio=tension.recovery_ratio,
            attention_count=tension.attention_count,
            db=ctx.db,
        )

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(MorningCheckinHandler())
