"""Handler for sacrifice_log intent."""

import logging

from app.bot.handlers.base import HandlerContext, IntentHandler
from app.bot.handlers.registry import REGISTRY
from app.models.sacrifice import Sacrifice as SacrificeModel
from app.services import capture as capture_service

logger = logging.getLogger(__name__)


class SacrificeLogHandler(IntentHandler):
    intent = "sacrifice_log"

    async def handle(self, ctx: HandlerContext) -> str:
        resource = capture_service.extract_resource_from_text(ctx.text)
        matched = (
            capture_service.match_goal_by_keywords(ctx.text, ctx.active_goals)
            or capture_service.match_goal_title(ctx.text, ctx.active_goals)
        )
        if matched:
            capture_service.record_sacrifice(ctx.db, matched.id, resource, ctx.text)
            count = (
                ctx.db.query(SacrificeModel)
                .filter(SacrificeModel.goal_id == matched.id)
                .count()
            )
            logger.debug(f"Sacrifice logged: goal={matched.title} resource={resource.value}")
            return (
                f"Logged — sacrifice attributed to {resource.value}. "
                f"{matched.title} sacrifice count now {count}."
            )
        logger.debug("Sacrifice: no goal matched")
        return "Sacrifice noted — which goal did it affect?"

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(SacrificeLogHandler())
