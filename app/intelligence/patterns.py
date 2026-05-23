"""Commitment profile synthesis from sacrifice attribution history.

Synthesises the willpower pattern (sacrifice counts by resource type)
and active goal state into a plain-language commitment profile.

This is a periodic synthesis — not a per-message response. It surfaces
which resource is being depleted most and what the pattern reveals.

planA rules: surface only, never advise.
"""

import logging

from app.services.resource import WillpowerPattern

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 400


def _pattern_context(pattern: WillpowerPattern, goals: list) -> str:
    """Build a structured summary of the commitment pattern for Claude."""
    lines = [
        f"Sacrifice count (28 days): {pattern.sacrifice_count_28d}",
        f"Dominant depleted resource: {pattern.dominant_resource or 'none'}",
        "",
        "By resource:",
    ]
    for resource, count in sorted(pattern.by_resource.items(), key=lambda x: -x[1]):
        lines.append(f"  {resource}: {count}")

    if goals:
        lines.append(f"\nActive goals: {len(goals)}")
        for g in goals:
            lines.append(f"  [{g.state.value}] {g.title}")

    return "\n".join(lines)


def synthesize_stub(pattern: WillpowerPattern) -> str:
    """Deterministic synthesis without Claude."""
    if pattern.sacrifice_count_28d == 0:
        return "No sacrifices logged in the past 28 days."
    parts = [f"{pattern.sacrifice_count_28d} sacrifices logged in the past 28 days."]
    if pattern.dominant_resource:
        parts.append(f"{pattern.dominant_resource.capitalize()} is the most depleted resource.")
    return " ".join(parts)


def synthesize(pattern: WillpowerPattern, goals: list, client) -> str:
    """Synthesize the user's commitment pattern into a plain language profile.

    Uses Claude when available; otherwise returns a structured stub.
    Never advises — surfaces the pattern only.
    """
    if client is None:
        return synthesize_stub(pattern)

    context = _pattern_context(pattern, goals)
    prompt = (
        "You are planA. Synthesise the following commitment pattern into a plain language profile. "
        "Surface what resource is being depleted most and what this pattern reveals. "
        "Do not advise what to do. Do not suggest dropping goals. "
        "Two to four sentences.\n\n"
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
        logger.error(f"Pattern synthesis failed: {e}")
        return synthesize_stub(pattern)
