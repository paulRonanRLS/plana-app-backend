"""Morning check-in conversation driver.

Builds a richer system prompt that includes resource data (not just goals)
and produces a contextual morning check-in response.

All Claude calls are synchronous — wrap with asyncio.to_thread when
calling from an async context (e.g. the Telegram handler).
"""

import logging
from datetime import datetime, timezone
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

_GARMIN_METRIC_TYPES = frozenset({
    "sleep_score",
    "sleep_duration_hours",
    "hrv",
    "resting_hr",
    "body_battery",
    "stress",
})

# Display order and labels for the system prompt
_METRIC_LABELS: dict[str, str] = {
    "sleep_score":          "Sleep score",
    "sleep_duration_hours": "Sleep duration",
    "hrv":                  "HRV",
    "resting_hr":           "Resting HR",
    "body_battery":         "Body battery",
    "stress":               "Stress",
}

_METRIC_UNITS: dict[str, str] = {
    "sleep_score":          "/100",
    "sleep_duration_hours": "h",
    "hrv":                  " ms",
    "resting_hr":           " bpm",
    "body_battery":         "/100",
    "stress":               "/100",
}

_METRIC_DECIMALS: dict[str, int] = {
    "sleep_score":          0,
    "sleep_duration_hours": 1,
    "hrv":                  0,
    "resting_hr":           0,
    "body_battery":         0,
    "stress":               0,
}


def _query_today_garmin(db) -> dict[str, float]:
    """Return today's Garmin MetricReadings as {metric_type_str: value}.

    Queries only the six overnight metrics. Returns an empty dict when no
    Garmin data has been ingested yet today or when db is None.
    """
    if db is None:
        return {}
    try:
        from app.models.metric_reading import MetricReading, MetricSource, MetricType

        start_of_day = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        target_types = [MetricType(t) for t in _GARMIN_METRIC_TYPES]
        rows = (
            db.query(MetricReading)
            .filter(
                MetricReading.source == MetricSource.garmin,
                MetricReading.timestamp >= start_of_day,
                MetricReading.metric_type.in_(target_types),
                MetricReading.value.isnot(None),
            )
            .all()
        )
        return {r.metric_type.value: r.value for r in rows}
    except Exception as exc:
        logger.warning(f"Garmin readings query failed: {exc}")
        return {}


def _format_garmin_readings(readings: dict[str, float]) -> list[str]:
    """Format readings dict into labelled lines, in canonical display order."""
    lines = []
    for key, label in _METRIC_LABELS.items():
        val = readings.get(key)
        if val is None:
            continue
        decimals = _METRIC_DECIMALS[key]
        unit = _METRIC_UNITS[key]
        lines.append(f"  {label}: {val:.{decimals}f}{unit}")
    return lines


def build_system_prompt(
    goals: list,
    *,
    time_envelope_hours: Optional[float] = None,
    recovery_envelope_tss: Optional[float] = None,
    time_ratio: Optional[float] = None,
    recovery_ratio: Optional[float] = None,
    attention_count: Optional[int] = None,
    garmin_readings: Optional[dict[str, float]] = None,
    db=None,
) -> str:
    """Build a context-rich system prompt for the morning check-in.

    Injects goal state, current resource capacity, and today's Garmin
    readings so Claude can reference actual numbers during the check-in.
    """
    from app.intelligence.week_context import build_week_context_lines

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

    lines.extend(build_week_context_lines(goals, db=db))

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

    if garmin_readings:
        reading_lines = _format_garmin_readings(garmin_readings)
        if reading_lines:
            lines.append(
                "Today's Garmin readings retrieved from the database "
                "(accurate — reference them directly when the user asks):"
            )
            lines.extend(reading_lines)
            lines.append("")
    else:
        lines.append(
            "No overnight health metrics have been received yet today. "
            "Do not mention data access or connectivity. "
            "Ask the user how they are feeling and note that their metrics will update shortly."
        )
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
    db=None,
) -> str:
    """Generate a contextual morning check-in response.

    Synchronous — use asyncio.to_thread when calling from async code.
    Falls back to stub when client is None or on API error.
    """
    if client is None:
        return _STUB

    garmin_readings = _query_today_garmin(db)

    system = build_system_prompt(
        goals,
        time_envelope_hours=time_envelope_hours,
        recovery_envelope_tss=recovery_envelope_tss,
        time_ratio=time_ratio,
        recovery_ratio=recovery_ratio,
        attention_count=attention_count,
        garmin_readings=garmin_readings,
        db=db,
    )

    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages[-20:],
            timeout=30.0,
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.error(f"Checkin response failed: {e}")
        return _STUB
