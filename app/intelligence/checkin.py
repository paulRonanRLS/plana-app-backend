"""Morning check-in conversation driver.

Builds a richer system prompt that includes resource data (not just goals)
and produces a contextual morning check-in response.

All Claude calls are synchronous — wrap with asyncio.to_thread when
calling from an async context (e.g. the Telegram handler).
"""

import logging
from typing import Optional

from app.models.goal import GoalState
from app.services.goal import TERMINAL_STATES

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 400

_STUB = (
    "Good morning. How are you feeling today — physically and mentally? "
    "Good, neutral, or flat?"
)


def build_system_prompt(
    goals: list,
    *,
    time_envelope_hours: Optional[float] = None,
    recovery_envelope_tss: Optional[float] = None,
    time_ratio: Optional[float] = None,
    recovery_ratio: Optional[float] = None,
    attention_count: Optional[int] = None,
) -> str:
    """Build a context-rich system prompt for the morning check-in.

    Injects goal state and current resource capacity so Claude can reference
    actual numbers when probing physical and mental state.
    """
    active = [g for g in goals if g.state not in TERMINAL_STATES]
    primacy = next((g for g in active if g.state == GoalState.primacy), None)

    lines = [
        "You are planA — a personal goal tracking companion.",
        "",
        "This is the morning check-in. Take a clear read on the user's physical",
        "and mental state and probe whether today's capacity matches their commitments.",
        "",
        "Rules:",
        "- Ask one short, direct question at a time.",
        "- Surface reality honestly. Do not minimise drift or fatigue.",
        "- Never tell the user what to do. Never recommend dropping or pausing a goal.",
        "- If something signals overload, name it clearly and ask for acknowledgement.",
        "",
    ]

    if primacy:
        lines.append(f"Primacy goal (inviolable): {primacy.title}")
        lines.append("")

    if active:
        lines.append("Active goals:")
        for g in active:
            desc = f" — {g.description}" if g.description else ""
            lines.append(f"  [{g.state.value}] {g.title}{desc}")
    else:
        lines.append("No active goals.")
    lines.append("")

    resource_values = [time_envelope_hours, time_ratio, recovery_envelope_tss,
                       recovery_ratio, attention_count]
    if any(v is not None for v in resource_values):
        lines.append("Current resource state:")
        if time_envelope_hours is not None and time_ratio is not None:
            committed = time_ratio * time_envelope_hours
            pct = time_ratio * 100
            lines.append(
                f"  Time: {committed:.0f}h committed of {time_envelope_hours:.0f}h "
                f"envelope ({pct:.0f}%)"
            )
        if recovery_envelope_tss is not None and recovery_ratio is not None:
            committed_tss = recovery_ratio * recovery_envelope_tss
            pct = recovery_ratio * 100
            lines.append(
                f"  Recovery: {committed_tss:.0f} TSS committed of "
                f"{recovery_envelope_tss:.0f} envelope ({pct:.0f}%)"
            )
        if attention_count is not None:
            lines.append(f"  Attention load: {attention_count} open items")
        lines.append("")

    return "\n".join(lines)


def build_response(
    messages: list[dict],
    goals: list,
    client,
    *,
    time_envelope_hours: Optional[float] = None,
    recovery_envelope_tss: Optional[float] = None,
    time_ratio: Optional[float] = None,
    recovery_ratio: Optional[float] = None,
    attention_count: Optional[int] = None,
) -> str:
    """Generate a contextual morning check-in response.

    Synchronous — use asyncio.to_thread when calling from async code.
    Falls back to stub when client is None or on API error.
    """
    if client is None:
        return _STUB

    system = build_system_prompt(
        goals,
        time_envelope_hours=time_envelope_hours,
        recovery_envelope_tss=recovery_envelope_tss,
        time_ratio=time_ratio,
        recovery_ratio=recovery_ratio,
        attention_count=attention_count,
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages[-20:],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Checkin response failed: {e}")
        return _STUB
