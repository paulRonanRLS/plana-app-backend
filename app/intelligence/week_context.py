"""Week context — date, week boundaries, and habit progress for system prompts.

Imported by both the bot handlers and the check-in intelligence module so the
same temporal context appears in all Claude system prompts.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _week_bounds() -> tuple[date, date]:
    """Return (monday, sunday) for the current ISO week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)


def _fmt_date(d: date) -> str:
    """Format a date as '1 June' (no leading zero on day)."""
    return f"{d.day} {d.strftime('%B')}"


def _query_habit_counts(db, goals: list) -> dict[int, int]:
    """Return {goal_id: count} of habit_log records this week per goal.

    Attribution is stored in two ways:
      1. text_value == str(goal_id)  — web app tick and Telegram captures that
         matched a goal (record_progress with goal_id; web log_habit endpoint)
      2. notes JSON contains {"goal_id": <int>}  — same records, notes confirms it

    Unattributed habit_logs (metric_log fallback, no goal match) have raw text
    in text_value and notes=None — these cannot be counted per goal.

    Returns an empty dict on any error or when db is None.
    """
    if db is None:
        return {}
    try:
        from app.models.metric_reading import MetricReading, MetricType
        import json as _json

        monday, _ = _week_bounds()
        week_start = datetime.combine(monday, datetime.min.time()).replace(tzinfo=timezone.utc)
        week_end = week_start + timedelta(days=7)

        goal_id_strings = {str(g.id) for g in goals if g.id is not None}
        if not goal_id_strings:
            return {}

        logger.debug(
            f"Habit count query: week {week_start.date()} – {week_end.date()}, "
            f"searching for goal IDs {goal_id_strings} "
            f"({', '.join(f'{g.id}={g.title!r}' for g in goals if g.id is not None)})"
        )

        rows = (
            db.query(MetricReading)
            .filter(
                MetricReading.metric_type == MetricType.habit_log,
                MetricReading.timestamp >= week_start,
                MetricReading.timestamp < week_end,
            )
            .all()
        )

        logger.debug(
            f"Habit count query: {len(rows)} habit_log rows this week total "
            f"(all sources, before goal-id filter)"
        )
        for row in rows:
            logger.debug(
                f"  row id={row.id} ts={row.timestamp.date()} source={row.source} "
                f"text_value={row.text_value!r} val={row.value} notes={row.notes!r}"
            )

        counts: dict[int, int] = defaultdict(int)
        for row in rows:
            # Primary path: text_value is the numeric goal ID
            if row.text_value in goal_id_strings:
                try:
                    counts[int(row.text_value)] += 1
                    continue
                except (ValueError, TypeError):
                    pass
            # Secondary path: goal_id stored in notes JSON
            if row.notes:
                try:
                    d = _json.loads(row.notes)
                    gid = d.get("goal_id")
                    if gid is not None and str(gid) in goal_id_strings:
                        counts[int(gid)] += 1
                except (ValueError, TypeError, AttributeError):
                    pass

        logger.debug(f"Habit count query result: {dict(counts)}")
        return dict(counts)
    except Exception as exc:
        logger.warning(f"Habit count query failed: {exc}")
        return {}


def build_week_context_lines(goals: list, db=None) -> list[str]:
    """Return system prompt lines for date, week, and habit progress.

    Always includes today's date and ISO week boundaries.
    When db is provided and there are active habit goals with weekly_target,
    also appends current-week progress for each such goal.

    Returns a list of strings ready to extend into a system prompt lines list.
    The list ends with a trailing empty string so callers get a blank line gap.
    """
    from app.services.goal import TERMINAL_STATES

    today = date.today()
    monday, sunday = _week_bounds()
    days_left = 6 - today.weekday()

    if days_left == 0:
        remaining_str = "last day of the week"
    elif days_left == 1:
        remaining_str = "1 day remaining"
    else:
        remaining_str = f"{days_left} days remaining"

    date_str = f"{today.strftime('%A')}, {_fmt_date(today)} {today.year}"
    week_str = f"{monday.strftime('%A')} {_fmt_date(monday)} – {sunday.strftime('%A')} {_fmt_date(sunday)} ({remaining_str})"

    lines = [
        f"Today: {date_str}",
        f"Week:  {week_str}",
    ]

    active = [g for g in goals if g.state not in TERMINAL_STATES]
    habit_goals = [g for g in active if g.weekly_target is not None]

    if habit_goals and db is not None:
        counts = _query_habit_counts(db, habit_goals)
        lines.append("Habit progress this week (from database — accurate):")
        for g in habit_goals:
            count = counts.get(g.id, 0)
            lines.append(f"  {g.title}: {count} of {g.weekly_target} this week")

    lines.append("")
    return lines
