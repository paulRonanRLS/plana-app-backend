"""Goal memoir drafting at completion or release.

Synthesises accumulated data (sacrifices made, milestones achieved or missed)
into a narrative reflection on the goal's lifecycle.

planA rules: honest about drift, no future advice.
"""

import logging

from app.models.goal import Goal

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 800


def _goal_context(goal: Goal, sacrifices: list, milestones: list) -> str:
    """Build a structured summary of the goal's history for Claude."""
    lines = [
        f"Goal: {goal.title}",
        f"Outcome: {goal.state.value}",
    ]
    if goal.description:
        lines.append(f"Description: {goal.description}")
    if goal.target_date:
        lines.append(f"Target date: {goal.target_date}")
    if goal.release_reason:
        lines.append(f"Release reason: {goal.release_reason}")

    achieved = [m for m in milestones if hasattr(m, "state") and m.state.value == "achieved"]
    missed = [m for m in milestones if hasattr(m, "state") and m.state.value == "missed"]

    if achieved:
        lines.append(f"\nMilestones achieved ({len(achieved)}):")
        for m in achieved:
            lines.append(f"  - {m.title}")
    if missed:
        lines.append(f"\nMilestones missed ({len(missed)}):")
        for m in missed:
            lines.append(f"  - {m.title}")

    if sacrifices:
        lines.append(f"\nSacrifices logged: {len(sacrifices)}")
        by_resource: dict[str, int] = {}
        for s in sacrifices:
            key = s.resource.value if hasattr(s.resource, "value") else str(s.resource)
            by_resource[key] = by_resource.get(key, 0) + 1
        for resource, count in sorted(by_resource.items(), key=lambda x: -x[1]):
            lines.append(f"  {resource}: {count}")

    return "\n".join(lines)


def _stub(goal: Goal) -> str:
    action = "completed" if goal.state.value == "completed" else "released"
    return f"Goal '{goal.title}' {action}. Enable Claude for a full memoir."


def draft(goal: Goal, sacrifices: list, milestones: list, client) -> str:
    """Draft a memoir for a completed or released goal.

    Written in first person from the user's perspective — honest about
    what was achieved and what was sacrificed, without future advice.
    Returns a stub when client is None.
    """
    if client is None:
        return _stub(goal)

    context = _goal_context(goal, sacrifices, milestones)

    prompt = (
        "You are planA. Draft a memoir for the following goal. "
        "Write in first person from the user's perspective. "
        "Be honest about what was achieved and what was sacrificed. "
        "Acknowledge drift or missed commitments without judgment. "
        "Do not advise or suggest future actions. "
        "Keep it under 200 words — clear and direct.\n\n"
        f"{context}"
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Memoir drafting failed: {e}")
        return _stub(goal)
