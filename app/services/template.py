"""Goal template library service.

Loads and queries config/goal_templates.json. Provides personalised target-range
suggestions for health foundation templates based on the user's last 90 days of
Garmin data.
"""

import json
import logging
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = Path(__file__).parent.parent.parent / "config" / "goal_templates.json"
_cache: Optional[dict] = None


def load_templates() -> dict:
    """Return the full parsed template library (cached after first load)."""
    global _cache
    if _cache is None:
        with open(_TEMPLATES_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache


def _all_templates() -> list[dict]:
    data = load_templates()
    templates = []
    for cat in data.get("categories", []):
        for tmpl in cat.get("templates", []):
            tmpl = dict(tmpl)
            tmpl["category_id"] = cat["id"]
            tmpl["category_label"] = cat["label"]
            templates.append(tmpl)
    return templates


def get_template(template_id: str) -> Optional[dict]:
    """Return a single template by id, or None if not found."""
    for tmpl in _all_templates():
        if tmpl["id"] == template_id:
            return tmpl
    return None


def list_templates_by_category() -> dict[str, dict]:
    """Return templates grouped by category.

    Returns:
        {category_id: {id, label, description, templates: [...]}}
    """
    data = load_templates()
    result = {}
    for cat in data.get("categories", []):
        result[cat["id"]] = {
            "id": cat["id"],
            "label": cat["label"],
            "description": cat.get("description", ""),
            "templates": cat.get("templates", []),
        }
    return result


# ── Personalised target-range suggestion ──────────────────────────────────────

def _percentile(data: list[float], p: float) -> float:
    """Compute the p-th percentile of data (0–100)."""
    s = sorted(data)
    n = len(s)
    if n == 0:
        return 0.0
    k = (n - 1) * p / 100
    lo = int(k)
    hi = lo + 1
    if hi >= n:
        return s[lo]
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def suggest_target_range(template: dict, db) -> dict:
    """Query last 90 days of MetricReadings and suggest personalised min/max.

    Returns:
        {
          "has_data": bool,
          "suggested_min": float | None,
          "suggested_max": float | None,
          "data_points": int,
          "note": str,
          "default_min": float,
          "default_max": float,
        }
    """
    default_min = template.get("default_min")
    default_max = template.get("default_max")
    direction = template.get("direction", "higher")
    no_data = {
        "has_data": False,
        "suggested_min": default_min,
        "suggested_max": default_max,
        "data_points": 0,
        "note": "Using default range — no personal data available yet.",
        "default_min": default_min,
        "default_max": default_max,
    }

    if not template.get("target_range_queryable"):
        return no_data
    if db is None:
        return no_data

    try:
        from app.models.metric_reading import MetricReading, MetricSource, MetricType

        metric_str = template.get("metric")
        if not metric_str:
            return no_data

        try:
            metric_type = MetricType(metric_str)
        except ValueError:
            return no_data

        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        rows = (
            db.query(MetricReading)
            .filter(
                MetricReading.metric_type == metric_type,
                MetricReading.source == MetricSource.garmin,
                MetricReading.timestamp >= cutoff,
                MetricReading.value.isnot(None),
            )
            .all()
        )
        values = [r.value for r in rows if r.value is not None]

        if len(values) < 7:
            return no_data

        p10 = _percentile(values, 10)
        p90 = _percentile(values, 90)
        mean = statistics.mean(values)

        if direction == "higher":
            # Target: don't fall below the 10th percentile of recent data
            suggested_min = max(default_min or 0, round(p10))
            suggested_max = default_max
        else:
            # Target: don't exceed the 90th percentile of recent data
            suggested_min = default_min
            suggested_max = min(default_max or 9999, round(p90))

        return {
            "has_data": True,
            "suggested_min": suggested_min,
            "suggested_max": suggested_max,
            "data_points": len(values),
            "mean": round(mean, 1),
            "note": f"Suggested from your last {len(values)} days of Garmin data.",
            "default_min": default_min,
            "default_max": default_max,
        }

    except Exception as exc:
        logger.warning(f"suggest_target_range failed for {template.get('id')}: {exc}")
        return no_data


# ── Build goal from template ───────────────────────────────────────────────────

def build_goal_from_template(template: dict, user_inputs: dict) -> dict:
    """Return a dict of goal fields ready to pass to the goal service.

    user_inputs may contain:
      title, description, target_date, target_min, target_max,
      weekly_target, habit_type, habit_unit, habit_period,
      capture_keywords, weekly_time_hours, weekly_tss,
      capability_data (dict of capability field values)
    """
    goal_type = template.get("goal_type", "achievement")
    title = user_inputs.get("title") or template.get("suggested_title", "")

    # Build description from template + capability data
    description_parts = []
    if user_inputs.get("description"):
        description_parts.append(user_inputs["description"])
    cap_data = user_inputs.get("capability_data", {})
    if cap_data:
        cap_lines = []
        for field in template.get("capability_fields", []):
            val = cap_data.get(field["id"])
            if val:
                cap_lines.append(f"{field['label']}: {val}")
        if cap_lines:
            description_parts.append("Capability baseline — " + ", ".join(cap_lines) + ".")
    description = " ".join(description_parts) or None

    result = {
        "title": title,
        "description": description,
        "goal_type": goal_type,
        "template_id": template["id"],
    }

    if goal_type == "perpetual":
        result["target_metric_type"] = template.get("metric")
        result["target_min"] = user_inputs.get("target_min", template.get("default_min"))
        result["target_max"] = user_inputs.get("target_max", template.get("default_max"))

    elif goal_type == "achievement":
        result["target_date"] = user_inputs.get("target_date")
        result["weekly_time_hours"] = user_inputs.get("weekly_time_hours")
        result["weekly_tss"] = user_inputs.get("weekly_tss")

    elif goal_type == "habit":
        result["habit_type"] = user_inputs.get("habit_type") or template.get("habit_type", "count")
        result["habit_unit"] = user_inputs.get("habit_unit") or template.get("habit_unit", "sessions")
        result["habit_period"] = user_inputs.get("habit_period") or template.get("habit_period", "week")
        result["weekly_target"] = user_inputs.get("weekly_target") or template.get("default_target")
        keywords = user_inputs.get("capture_keywords") or template.get("capture_keywords", [])
        result["capture_keywords"] = keywords

    return result
