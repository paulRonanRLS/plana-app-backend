"""Goal query intelligence — data-driven answers about goal progress.

Builds structured context from milestones and sacrifice history before calling
Claude, so answers reference actual state rather than reasoning from titles only.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.goal import Goal
from app.models.sacrifice import Sacrifice
from app.services.goal import TERMINAL_STATES
from app.services.milestone import list_milestones

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 400

_SYSTEM_PROMPT = """\
You are planA — a personal goal tracking companion.
Answer the user's question using the structured goal data provided below.
Be factual and concise. Reference milestone states and dates when relevant.
Surface reality honestly — if progress is behind schedule or sacrifices are \
high, name it plainly.
Never tell the user what to do. Never recommend changing or releasing a goal."""


def build_response(
    text: str,
    goals: list,
    db: Session,
    client,
) -> str:
    """Generate a data-driven answer to a goal query.

    Falls back to _stub_response() when client is None or on any error.
    """
    if client is None:
        return _stub_response(goals, db)

    context = build_context(goals, db)
    prompt = f"{context}\n\nUser question: {text}"

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Goal query Claude call failed: {e}")
        return _stub_response(goals, db)


def build_context(goals: list, db: Session) -> str:
    """Return a structured text block covering all non-terminal goals.

    For each goal: state, metadata, milestone progression, and sacrifice count
    over the last 30 days.
    """
    active = [g for g in goals if g.state not in TERMINAL_STATES]
    if not active:
        return "No active goals."

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).date()
    sections = []
    for goal in active:
        sections.extend(_goal_section(goal, db, sacrifice_cutoff=cutoff))
        sections.append("")

    return "\n".join(sections).strip()


def _goal_section(goal: Goal, db: Session, sacrifice_cutoff) -> list[str]:
    lines = []

    header = f"[{goal.state.value}] {goal.title}"
    if goal.description:
        header += f" — {goal.description}"
    lines.append(header)

    meta: list[str] = []
    if goal.goal_type:
        meta.append(f"type={goal.goal_type.value}")
    if goal.target_date:
        meta.append(f"target={goal.target_date.isoformat()}")
    if goal.weekly_time_hours:
        meta.append(f"time={goal.weekly_time_hours:.0f}h/week")
    if goal.weekly_target:
        meta.append(f"frequency={goal.weekly_target}x/week")
    if meta:
        lines.append("  " + "  ".join(meta))

    milestones = list_milestones(db, goal.id)
    if milestones:
        lines.append(f"  Milestones ({len(milestones)}):")
        for m in milestones:
            date_str = f" by {m.target_date.isoformat()}" if m.target_date else ""
            achieved_str = ""
            if m.achieved_at:
                achieved_str = f"  achieved {m.achieved_at.strftime('%d %b')}"
            lines.append(
                f"    {m.sequence}. [{m.state.value}] {m.title}{date_str}{achieved_str}"
            )
    else:
        lines.append("  Milestones: none")

    recent = (
        db.query(Sacrifice)
        .filter(Sacrifice.goal_id == goal.id, Sacrifice.date >= sacrifice_cutoff)
        .order_by(Sacrifice.date.desc())
        .all()
    )
    if recent:
        summary = ", ".join(s.resource.value for s in recent[:3])
        suffix = f" ({summary}{'…' if len(recent) > 3 else ''})"
        lines.append(f"  Sacrifices (last 30 days): {len(recent)}{suffix}")
    else:
        lines.append("  Sacrifices (last 30 days): 0")

    return lines


def _stub_response(goals: list, db: Session) -> str:
    """Deterministic fallback when Claude is unavailable."""
    active = [g for g in goals if g.state not in TERMINAL_STATES]
    if not active:
        return "No active goals."

    lines = []
    for goal in active:
        milestones = list_milestones(db, goal.id)
        achieved = sum(1 for m in milestones if m.state.value == "achieved")
        total = len(milestones)
        lines.append(f"{goal.title}: {achieved}/{total} milestones achieved")
    return "\n".join(lines)
