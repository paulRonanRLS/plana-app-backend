"""Handler for milestone_complete intent."""

import logging

from app.bot.handlers.base import HandlerContext, IntentHandler
from app.bot.handlers.registry import REGISTRY
from app.models.milestone import MilestoneState
from app.services import capture as capture_service
from app.services.milestone import list_milestones, update_milestone

logger = logging.getLogger(__name__)


class MilestoneCompleteHandler(IntentHandler):
    intent = "milestone_complete"

    async def handle(self, ctx: HandlerContext) -> str:
        all_milestones = []
        for g in ctx.active_goals:
            all_milestones.extend(list_milestones(ctx.db, g.id))
        open_milestones = [
            m for m in all_milestones
            if m.state not in (MilestoneState.achieved, MilestoneState.missed)
        ]
        matched = capture_service.match_milestone_title(ctx.text, open_milestones)
        if matched:
            update_milestone(
                ctx.db, matched.goal_id, matched.id,
                {"state": MilestoneState.achieved},
            )
            remaining = sorted(
                [m for m in open_milestones
                 if m.goal_id == matched.goal_id and m.id != matched.id],
                key=lambda m: m.sequence,
            )
            logger.debug(f"Milestone achieved: {matched.title}")
            if remaining:
                nxt = remaining[0]
                due = f" — due {nxt.target_date.isoformat()}" if nxt.target_date else ""
                return f"Milestone marked complete. {nxt.title} is next{due}."
            return "Milestone marked complete. No more pending milestones for that goal."
        logger.debug("Milestone complete: no milestone matched")
        return "I couldn't match that to a milestone — which one did you complete?"

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(MilestoneCompleteHandler())
