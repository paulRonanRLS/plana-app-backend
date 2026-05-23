"""Plain language description of detected resource conflicts.

Converts the structured ResourceTension dataclass into a readable summary
suitable for the tension map view or a Telegram response.

planA rules: surface only, never advise.
"""

import logging

from app.services.resource import ResourceTension

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 300


def _tension_context(tension: ResourceTension) -> str:
    """Build a structured description of resource state for Claude."""
    lines = [
        f"Time: {tension.total_committed_time_hours:.0f}h committed of "
        f"{tension.time_envelope_hours:.0f}h envelope ({tension.time_ratio * 100:.0f}%)",
        f"Recovery: {tension.total_committed_tss:.0f} TSS committed of "
        f"{tension.recovery_envelope_tss:.0f} envelope ({tension.recovery_ratio * 100:.0f}%)",
        f"Attention: {tension.attention_count} open items",
    ]
    if tension.goals:
        lines.append("")
        lines.append("Goal breakdown:")
        for g in tension.goals:
            lines.append(
                f"  {g.goal_title} [{g.goal_state}]: "
                f"{g.time_hours:.0f}h, {g.tss:.0f} TSS "
                f"({g.time_share * 100:.0f}% of time)"
            )
    return "\n".join(lines)


def describe_stub(tension: ResourceTension) -> str:
    """Deterministic tension description without Claude."""
    parts = []

    if tension.time_ratio > 1.0:
        parts.append(f"Time is over-committed at {tension.time_ratio * 100:.0f}% of envelope.")
    elif tension.time_ratio > 0.85:
        parts.append(f"Time is tightly committed at {tension.time_ratio * 100:.0f}% of envelope.")
    else:
        parts.append(f"Time has headroom — {tension.time_ratio * 100:.0f}% of envelope in use.")

    if tension.recovery_ratio > 1.0:
        parts.append(f"Recovery is over-committed at {tension.recovery_ratio * 100:.0f}% of TSS envelope.")
    elif tension.recovery_ratio > 0.85:
        parts.append(f"Recovery is tight at {tension.recovery_ratio * 100:.0f}% of TSS envelope.")
    else:
        parts.append(f"Recovery has headroom — {tension.recovery_ratio * 100:.0f}% of TSS envelope in use.")

    if tension.attention_count > 5:
        parts.append(f"Attention load is high: {tension.attention_count} open items.")
    elif tension.attention_count > 0:
        parts.append(f"Attention: {tension.attention_count} open items.")

    return " ".join(parts)


def describe(tension: ResourceTension, client) -> str:
    """Generate a plain language tension description.

    Uses Claude when available; otherwise returns a structured stub.
    Never advises what to do — surfaces the state only.
    """
    if client is None:
        return describe_stub(tension)

    context = _tension_context(tension)
    prompt = (
        "You are planA. Describe the following resource tension in plain language. "
        "Be direct. Surface over-commitment clearly. Do not advise what to do. "
        "Two or three sentences maximum.\n\n"
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
        logger.error(f"Tension description failed: {e}")
        return describe_stub(tension)
