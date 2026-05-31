"""Base class, context dataclass, and shared helpers for intent handlers."""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app.models.goal import GoalState
from app.services import capture as capture_service
from app.services.goal import TERMINAL_STATES

logger = logging.getLogger(__name__)

MAX_HISTORY = 20
_CAPTURE_INTENTS = frozenset({"physical_state", "illness_log", "metric_log"})


@dataclass
class HandlerContext:
    text: str
    intent: str
    original_intent: str
    is_morning: bool
    goals: list
    db: object
    claude_client: object
    redis_client: object
    pending_capture: Optional[dict]
    pending_alert: Optional[dict]
    messages: list = field(default_factory=list)
    confidence: float = 0.7

    @property
    def active_goals(self) -> list:
        return [g for g in self.goals if g.state not in TERMINAL_STATES]


class IntentHandler(ABC):
    intent: str

    @abstractmethod
    async def handle(self, ctx: HandlerContext) -> str:
        ...

    def writes_to_db(self) -> bool:
        return False

    def uses_pending_capture(self) -> bool:
        return False


def write_capture(db, intent: str, text: str) -> None:
    """Persist a MetricReading for physical/illness/metric intents."""
    if intent not in _CAPTURE_INTENTS:
        return
    try:
        if intent == "physical_state":
            capture_service.record_physical_state(db, text)
        elif intent == "illness_log":
            capture_service.record_illness(db, text)
        elif intent == "metric_log":
            capture_service.record_metric(db, text)
        logger.debug(f"Capture persisted: intent={intent}")
    except Exception as e:
        logger.error(f"Capture persist failed for intent={intent}: {e}")


def build_goals_system_prompt(goals: list) -> str:
    """Inject current goal state into the system prompt."""
    active = [g for g in goals if g.state not in TERMINAL_STATES]
    primacy = next((g for g in active if g.state == GoalState.primacy), None)

    lines = [
        "You are planA — a personal goal tracking companion.",
        "",
        "Surface reality honestly. Acknowledge drift or missed commitments when you see them.",
        "Never tell the user what to do. Never recommend dropping or pausing a goal.",
        "Ask one short, direct question at a time.",
        "When structured data has been provided earlier in this conversation it came from "
        "real database queries and is accurate. Do not retract or second-guess it.",
        "",
    ]

    if primacy:
        lines.append(f"Primacy goal (inviolable — no sacrifice expected): {primacy.title}")
        lines.append("")

    if active:
        lines.append("Active goals:")
        for g in active:
            lines.append(f"  [{g.state.value}] {g.title}")
    else:
        lines.append("No active goals.")

    return "\n".join(lines)


async def claude_response(messages: list, system_prompt: str, client) -> str:
    """Call Claude in a thread; returns error string on failure."""
    try:
        trimmed = messages[-MAX_HISTORY:]
        resp = await asyncio.to_thread(
            client.messages.create,
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=system_prompt,
            messages=trimmed,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Claude response failed: {e}")
        return "Something went wrong — try again in a moment."
