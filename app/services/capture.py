"""Capture service — persist Telegram bot messages as MetricReadings.

Called by the handler after intent classification. Each capture intent writes
one row to the metric_readings hypertable with MetricSource.telegram.
"""

import json
import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.metric_reading import MetricReading, MetricSource, MetricType
from app.models.sacrifice import ResourceType, Sacrifice

logger = logging.getLogger(__name__)

# Maximum text stored in text_value to avoid bloating the hypertable.
_TEXT_LIMIT = 500


def match_goal_title(text: str, goals: list) -> Optional[Any]:
    """Return the first non-terminal goal whose title appears in text (word-boundary match).

    Case-insensitive. Matches the full goal title as a contiguous word sequence, so
    goal "Run" won't match "running" but goal "Cooking" will match "cooking goal".
    Returns None if no goal matches.
    """
    low = text.lower()
    for goal in goals:
        pattern = r"\b" + re.escape(goal.title.lower()) + r"\b"
        if re.search(pattern, low):
            return goal
    return None


def match_goal_by_keywords(text: str, goals: list) -> Optional[Any]:
    """Return the first goal whose capture_keywords appear in text.

    Keywords are stored as a JSON array in goal.capture_keywords. Each keyword is
    matched as a whole word (word-boundary). Returns None if no match.
    """
    import json as _json
    low = text.lower()
    for goal in goals:
        if not goal.capture_keywords:
            continue
        try:
            keywords = _json.loads(goal.capture_keywords)
        except (ValueError, TypeError):
            continue
        for kw in keywords:
            if not kw:
                continue
            pattern = r"\b" + re.escape(kw.lower()) + r"\b"
            if re.search(pattern, low):
                return goal
    return None


def record_progress(db: Session, text: str, goal_id: Optional[int] = None) -> MetricReading:
    """Write a habit_log record for a progress_capture message.

    When goal_id is provided, stores it in text_value (per habit_log design) and
    keeps the original message text in notes JSON.  When omitted, stores the message
    text directly in text_value (unattributed capture).
    """
    if goal_id is not None:
        notes = json.dumps({"goal_id": goal_id, "text": text[:_TEXT_LIMIT]})
        return _write(db, MetricType.habit_log, text_value=str(goal_id), notes=notes)
    return _write(db, MetricType.habit_log, text_value=text[:_TEXT_LIMIT])


def record_physical_state(db: Session, text: str) -> MetricReading:
    """Write a physical_state record."""
    return _write(db, MetricType.physical_state, text_value=text[:_TEXT_LIMIT])


def record_illness(db: Session, text: str) -> MetricReading:
    """Write an illness_log record."""
    return _write(db, MetricType.illness_log, text_value=text[:_TEXT_LIMIT])


def record_metric(db: Session, text: str) -> MetricReading:
    """Extract value and metric type from text and write a MetricReading."""
    metric_type, value = _parse_metric(text)
    return _write(db, metric_type, value=value, text_value=text[:_TEXT_LIMIT])


# ── Sacrifice capture ──────────────────────────────────────────────────────────

# Ordered by specificity — first matching resource wins.
_RESOURCE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "recovery": ("tired", "exhausted", "fatigued", "sore", "recovery", "energy", "depleted"),
    "attention": ("distracted", "focus", "attention", "overwhelmed", "scattered", "stress"),
    "willpower": ("motivation", "willpower", "couldn't face", "mental", "burnout", "drained"),
    "time": ("time", "work", "meeting", "busy", "schedule", "commitment", "appointment", "deadline"),
}


def extract_resource_from_text(text: str) -> ResourceType:
    """Infer which of the four resources was depleted from natural language.

    Returns ResourceType.time as default when no keyword matches.
    """
    low = text.lower()
    for resource, keywords in _RESOURCE_KEYWORDS.items():
        if any(k in low for k in keywords):
            return ResourceType(resource)
    return ResourceType.time


def record_sacrifice(
    db: Session, goal_id: int, resource: ResourceType, text: str
) -> Sacrifice:
    """Write a Sacrifice record attributed to the given goal and resource."""
    s = Sacrifice(
        goal_id=goal_id,
        date=date.today(),
        resource=resource,
        notes=text[:_TEXT_LIMIT],
        created_at=datetime.now(timezone.utc),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── Milestone matching ─────────────────────────────────────────────────────────

def match_milestone_title(text: str, milestones: list) -> Optional[Any]:
    """Return the first milestone whose title appears in text (word-boundary match).

    Case-insensitive. Returns None if no milestone matches.
    """
    low = text.lower()
    for m in milestones:
        pattern = r"\b" + re.escape(m.title.lower()) + r"\b"
        if re.search(pattern, low):
            return m
    return None


# ── Goal state parsing ─────────────────────────────────────────────────────────

_STATE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "primacy": ("plana", "planA", "primacy", "as my priority", "top priority", "my priority goal"),
    "subordinate": ("subordinate", "background", "secondary", "back burner"),
    "active": ("back to active", "set active", "make active", "active again"),
    "drifting": ("drifting", "mark as drift"),
}


def extract_target_state_from_text(text: str) -> Optional[str]:
    """Parse the intended goal state from natural language.

    Returns one of "primacy", "active", "subordinate", "drifting", or None.
    """
    low = text.lower()
    for state, keywords in _STATE_KEYWORDS.items():
        if any(k in low for k in keywords):
            return state
    return None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_metric(text: str) -> tuple[MetricType, Optional[float]]:
    """Infer MetricType and numeric value from natural language."""
    low = text.lower()
    value = _extract_number(text)
    if any(w in low for w in ("kg", "lb", "lbs", "weight", "weigh")):
        return MetricType.weight, value
    if any(w in low for w in ("unit", "units", "drink", "drinks", "glass", "glasses",
                               "beer", "wine", "alcohol")):
        return MetricType.alcohol_units, value
    # No recognised metric type — store as habit_log so nothing is lost.
    return MetricType.habit_log, value


def _extract_number(text: str) -> Optional[float]:
    """Return the first integer or decimal found in text, or None."""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def _write(
    db: Session,
    metric_type: MetricType,
    *,
    value: Optional[float] = None,
    text_value: Optional[str] = None,
    notes: Optional[str] = None,
) -> MetricReading:
    return _persist(db, [{
        "timestamp": datetime.now(timezone.utc),
        "metric_type": metric_type,
        "value": value,
        "text_value": text_value,
        "source": MetricSource.telegram,
        "notes": notes,
    }])[0]


def _persist(db: Session, row_dicts: list[dict]) -> list[MetricReading]:
    """Insert MetricReading rows.

    Tries without explicit IDs first (PostgreSQL sequence). Falls back to
    explicit IDs on IntegrityError so SQLite test databases work too.
    """
    def _build(id_offset: Optional[int]) -> list[MetricReading]:
        max_id = 0
        if id_offset is not None:
            max_id = db.query(func.max(MetricReading.id)).scalar() or 0
        rows = []
        for i, r in enumerate(row_dicts):
            row = MetricReading(
                timestamp=r["timestamp"],
                metric_type=r["metric_type"],
                value=r.get("value"),
                text_value=r.get("text_value"),
                source=r.get("source", MetricSource.telegram),
                notes=r.get("notes"),
            )
            if id_offset is not None:
                row.id = max_id + i + 1
            db.add(row)
            rows.append(row)
        return rows

    rows = _build(id_offset=None)
    try:
        db.commit()
        return rows
    except IntegrityError:
        db.rollback()
        rows = _build(id_offset=0)
        db.commit()
        return rows
