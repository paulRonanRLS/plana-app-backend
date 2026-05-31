"""Handler for goal_state_change intent."""

import logging

from fastapi import HTTPException

from app.bot.handlers.base import HandlerContext, IntentHandler
from app.bot.handlers.registry import REGISTRY
from app.services import capture as capture_service
from app.services import goal as goal_service

logger = logging.getLogger(__name__)


class GoalStateChangeHandler(IntentHandler):
    intent = "goal_state_change"

    async def handle(self, ctx: HandlerContext) -> str:
        target_state = capture_service.extract_target_state_from_text(ctx.text)
        matched = (
            capture_service.match_goal_by_keywords(ctx.text, ctx.active_goals)
            or capture_service.match_goal_title(ctx.text, ctx.active_goals)
        )
        if not matched:
            return "Which goal did you want to change the state of?"
        if not target_state:
            return "What state? (planA, active, subordinate)"
        try:
            if target_state == "primacy":
                goal_service.set_primacy(ctx.db, matched.id)
                response = f"Done — {matched.title} is now planA."
            elif target_state == "active":
                goal_service.activate_goal(ctx.db, matched.id)
                response = f"Done — {matched.title} is now active."
            elif target_state == "subordinate":
                goal_service.set_subordinate(ctx.db, matched.id)
                response = f"Done — {matched.title} is now subordinate."
            elif target_state == "drifting":
                goal_service.mark_drifting(ctx.db, matched.id)
                response = f"Done — {matched.title} flagged as drifting."
            else:
                response = "What state? (planA, active, subordinate)"
            logger.debug(f"State change: goal={matched.title} → {target_state}")
            return response
        except HTTPException as exc:
            logger.warning(f"State change failed: {exc.detail}")
            return f"Couldn't change state: {exc.detail}"

    def writes_to_db(self) -> bool:
        return True


REGISTRY.register(GoalStateChangeHandler())
