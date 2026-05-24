"""Milestone generation from goal metadata and capability baseline.

Two entry points:

  generate(goal, client) — original simple version, used by existing callers.
    Returns [] in stub mode.

  generate_milestones(goal, capability_baseline, client) — richer version that
    incorporates current fitness data into the prompt.
    Returns 3 generic milestones in stub mode.
"""

import json
import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

from app.models.goal import Goal

if TYPE_CHECKING:
    from app.services.capability import CapabilityBaseline

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 800


# ── Stub milestones ────────────────────────────────────────────────────────────

def _stub_milestones(goal: Goal, today: Optional[date] = None) -> list[dict]:
    """Three generic milestones spaced evenly across the goal timeline."""
    today = today or date.today()
    target = goal.target_date

    if target and target > today:
        span = (target - today).days
        d1 = today + timedelta(days=span // 3)
        d2 = today + timedelta(days=2 * span // 3)
        d3 = target
    else:
        d1 = today + timedelta(weeks=4)
        d2 = today + timedelta(weeks=8)
        d3 = today + timedelta(weeks=12)

    return [
        {
            "title": "Foundation",
            "description": f"Establish consistent baseline progress toward: {goal.title}.",
            "target_date": str(d1),
            "sequence": 1,
            "state": "suggested",
        },
        {
            "title": "Build",
            "description": f"Increase volume and intensity in pursuit of: {goal.title}.",
            "target_date": str(d2),
            "sequence": 2,
            "state": "suggested",
        },
        {
            "title": "Peak",
            "description": f"Final preparation and execution for: {goal.title}.",
            "target_date": str(d3),
            "sequence": 3,
            "state": "suggested",
        },
    ]


# ── Capability context formatting ──────────────────────────────────────────────

def _format_baseline(baseline: "CapabilityBaseline") -> Optional[str]:
    """Return a human-readable capability summary for the Claude prompt, or None."""
    if baseline.goal_type == "run":
        lines = ["Current running capability:"]
        if baseline.long_run_km:
            lines.append(f"  Long run (last 4 weeks): {baseline.long_run_km:.1f} km")
        if baseline.weekly_volume_km:
            lines.append(f"  Weekly volume (90-day avg): {baseline.weekly_volume_km:.1f} km/week")
        if baseline.avg_pace_min_per_km:
            lines.append(f"  Average pace: {baseline.avg_pace_min_per_km:.1f} min/km")
        if baseline.run_count:
            lines.append(f"  Activities in baseline: {baseline.run_count} runs")
        return "\n".join(lines) if len(lines) > 1 else None

    if baseline.goal_type == "ride":
        lines = ["Current cycling capability:"]
        if baseline.ftp_estimate_w:
            lines.append(f"  Estimated FTP: {baseline.ftp_estimate_w:.0f} W")
        if baseline.longest_ride_km:
            lines.append(f"  Longest ride (90 days): {baseline.longest_ride_km:.0f} km")
        if baseline.weekly_tss:
            lines.append(f"  Weekly TSS (90-day avg): {baseline.weekly_tss:.0f}")
        if baseline.ride_count:
            lines.append(f"  Activities in baseline: {baseline.ride_count} rides")
        return "\n".join(lines) if len(lines) > 1 else None

    return None


# ── Core generation ────────────────────────────────────────────────────────────

def generate_milestones(
    goal: Goal,
    capability_baseline: "CapabilityBaseline",
    client,
    *,
    today: Optional[date] = None,
) -> list[dict]:
    """Generate a milestone progression incorporating current fitness data.

    Returns 3 generic stub milestones when client is None (CLAUDE_ENABLED=false).
    Returns [] on any Claude error to fail safe.

    Each dict: title (str), description (str), target_date (str|None), sequence (int).
    """
    today = today or date.today()

    if client is None:
        return _stub_milestones(goal, today)

    goal_lines = [f"Goal: {goal.title}"]
    if goal.description:
        goal_lines.append(f"Description: {goal.description}")
    goal_lines.append(
        f"Target date: {goal.target_date}" if goal.target_date else "No fixed deadline"
    )
    goal_lines.append(f"Today: {today}")
    goal_context = "\n".join(goal_lines)

    baseline_context = _format_baseline(capability_baseline)

    prompt_parts = [
        "Generate a realistic milestone progression for this goal, "
        "taking into account the user's current capability.\n",
        goal_context,
    ]
    if baseline_context:
        prompt_parts.append(f"\n{baseline_context}")

    prompt_parts.append(
        "\nReturn a JSON array of 3 to 5 milestone objects. Each object must have:\n"
        "  title (str) — short milestone name\n"
        "  description (str) — what success looks like, measurable and specific\n"
        "  target_date (str YYYY-MM-DD or null)\n"
        "  sequence (int, starting 1)\n\n"
        "Build a logical progression from current capability to the goal. "
        "Make each step concrete and achievable. "
        "Return ONLY valid JSON, no other text."
    )

    prompt = "\n".join(prompt_parts)

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        milestones = json.loads(text)
        if not isinstance(milestones, list):
            return []
        return [m for m in milestones if isinstance(m, dict) and "title" in m]
    except Exception as e:
        logger.error(f"Milestone generation failed: {e}")
        return []


# ── Original simple entry point (kept for backward compatibility) ──────────────

def generate(goal: Goal, client, *, today: Optional[date] = None) -> list[dict]:
    """Generate a milestone progression without capability context.

    Returns a list of dicts with keys: title, description, target_date.
    Returns [] in stub mode or on error.
    """
    if client is None:
        return []

    today = today or date.today()
    lines = [f"Goal: {goal.title}"]
    if goal.description:
        lines.append(f"Description: {goal.description}")
    lines.append(f"Target date: {goal.target_date}" if goal.target_date else "No fixed deadline")
    lines.append(f"Today: {today}")
    goal_context = "\n".join(lines)

    prompt = (
        "Generate a milestone progression for the following goal.\n"
        "Return a JSON array of objects with keys:\n"
        "  title (str), description (str), target_date (str YYYY-MM-DD or null)\n"
        "Generate 3 to 5 milestones that form a logical progression toward the goal. "
        "Be concrete and measurable. Return ONLY valid JSON, no other text.\n\n"
        f"{goal_context}"
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text.strip()
        milestones = json.loads(text)
        if not isinstance(milestones, list):
            return []
        return [m for m in milestones if isinstance(m, dict) and "title" in m]
    except Exception as e:
        logger.error(f"Milestone generation failed: {e}")
        return []
