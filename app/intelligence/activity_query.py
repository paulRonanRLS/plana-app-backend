"""Activity query intelligence — natural language response for past activity lookups."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 300

_SYSTEM_PROMPT = (
    "You are planA, a personal goal tracking companion. "
    "Answer questions about past training activities factually and concisely. "
    "Include distance, duration, and any notable metrics (TSS, HR, power). "
    "If no activities are found, say so plainly. "
    "Never invent data. Never advise what the user should do next."
)


def build_response(
    user_text: str,
    activities: list[dict],
    client,
) -> str:
    """Return a natural language answer about the queried activities.

    Falls back to _format_stub() when client is None or on error.
    """
    if client is None:
        return _format_stub(activities)

    context = _format_context(activities)
    prompt = f"{context}\n\nUser question: {user_text}"

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Activity query Claude call failed: {e}")
        return _format_stub(activities)


def _format_stub(activities: list[dict]) -> str:
    """Deterministic formatted response without Claude."""
    if not activities:
        return "No activities found for that period."

    lines = []
    for a in activities:
        name = a.get("name") or a.get("sport_type") or "Activity"
        distance_km = (a.get("distance_m") or 0) / 1000
        moving_s = a.get("moving_time_s") or 0
        mins, secs = divmod(int(moving_s), 60)
        hrs, mins = divmod(mins, 60)

        parts = [name]
        if distance_km > 0:
            parts.append(f"{distance_km:.1f} km")
        if moving_s > 0:
            if hrs:
                parts.append(f"{hrs}h {mins}m")
            else:
                parts.append(f"{mins}m {secs:02d}s")
        tss = a.get("tss")
        if tss:
            parts.append(f"TSS {tss:.0f}")

        lines.append(" · ".join(parts))

    return "\n".join(lines)


def _format_context(activities: list[dict]) -> str:
    """Build a structured context string for Claude."""
    if not activities:
        return "No activities found for the requested period."

    lines = [f"Found {len(activities)} activit{'y' if len(activities) == 1 else 'ies'}:"]
    for a in activities:
        ts = a.get("timestamp")
        date_str = ts.strftime("%a %d %b") if ts else "unknown date"
        name = a.get("name") or "Untitled"
        sport = a.get("sport_type") or ""
        distance_km = (a.get("distance_m") or 0) / 1000
        moving_s = a.get("moving_time_s") or 0
        mins, secs = divmod(int(moving_s), 60)
        hrs, mins = divmod(mins, 60)

        row = f"  {date_str}: {name}"
        if sport:
            row += f" ({sport})"
        if distance_km > 0:
            row += f", {distance_km:.2f} km"
        if moving_s > 0:
            if hrs:
                row += f", {hrs}h {mins}m"
            else:
                row += f", {mins}m {secs:02d}s"
        tss = a.get("tss")
        if tss:
            row += f", TSS {tss:.0f}"
        np_w = a.get("normalized_power_w")
        if np_w:
            row += f", NP {np_w:.0f}W"
        avg_hr = a.get("average_hr")
        if avg_hr:
            row += f", avg HR {avg_hr:.0f}"

        lines.append(row)

    return "\n".join(lines)
