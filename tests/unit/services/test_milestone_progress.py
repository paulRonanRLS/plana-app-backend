"""Unit tests for app/services/milestone_progress.py."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.goal import Goal, GoalState, GoalType
from app.models.milestone import Milestone, MilestoneState, ProgressMetric, ProgressPeriod, ProgressType
from app.services.milestone_progress import (
    _activity_matches_milestone,
    _extract_metric_value,
    _normalise_activity_type,
    _period_has_reset,
    activity_dict_from_row,
    process_activity,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_goal(db, title: str = "Half marathon") -> Goal:
    g = Goal(
        title=title,
        state=GoalState.active,
        goal_type=GoalType.achievement,
        created_at=_now(),
        updated_at=_now(),
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def _make_milestone(
    db,
    goal_id: int,
    *,
    activity_type: str = "run",
    progress_type: ProgressType = ProgressType.cumulative,
    metric: ProgressMetric = ProgressMetric.distance_km,
    target_value: float = 45.0,
    period: ProgressPeriod = ProgressPeriod.week,
    current_value: float = 0.0,
    state: MilestoneState = MilestoneState.pending,
    updated_at: datetime | None = None,
) -> Milestone:
    m = Milestone(
        goal_id=goal_id,
        title="Test milestone",
        state=state,
        sequence=1,
        activity_type=activity_type,
        progress_type=progress_type,
        metric=metric,
        target_value=target_value,
        period=period,
        current_value=current_value,
        created_at=_now(),
        updated_at=updated_at or _now(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def _run_activity(distance_km: float = 10.0, moving_time_s: int = 3600,
                  tss: float | None = None, ts: datetime | None = None) -> dict:
    return {
        "activity_type": "Run",
        "distance_km": distance_km,
        "moving_time_s": moving_time_s,
        "tss": tss,
        "timestamp": ts or _now(),
    }


# ── _normalise_activity_type ───────────────────────────────────────────────────

def test_normalise_run():
    assert _normalise_activity_type("Run") == "run"


def test_normalise_ride():
    assert _normalise_activity_type("Ride") == "ride"


def test_normalise_virtualrun():
    assert _normalise_activity_type("VirtualRun") == "run"


def test_normalise_hike():
    assert _normalise_activity_type("Hike") == "walk"


def test_normalise_unknown():
    assert _normalise_activity_type("Yoga") == "yoga"


# ── _activity_matches_milestone ────────────────────────────────────────────────

def test_match_exact():
    assert _activity_matches_milestone("run", "run") is True


def test_match_any():
    assert _activity_matches_milestone("ride", "any") is True


def test_no_match_different_type():
    assert _activity_matches_milestone("ride", "run") is False


def test_no_match_none_milestone_type():
    assert _activity_matches_milestone("run", None) is False


def test_match_case_insensitive():
    assert _activity_matches_milestone("run", "Run") is True


# ── _extract_metric_value ──────────────────────────────────────────────────────

def test_extract_distance():
    assert _extract_metric_value({"distance_km": 10.2}, ProgressMetric.distance_km) == 10.2


def test_extract_duration_min():
    val = _extract_metric_value({"moving_time_s": 3600}, ProgressMetric.duration_min)
    assert val == 60.0


def test_extract_tss():
    assert _extract_metric_value({"tss": 85.0}, ProgressMetric.tss) == 85.0


def test_extract_count():
    assert _extract_metric_value({}, ProgressMetric.count) == 1.0


def test_extract_distance_missing_returns_none():
    assert _extract_metric_value({}, ProgressMetric.distance_km) is None


def test_extract_tss_missing_returns_none():
    assert _extract_metric_value({"tss": None}, ProgressMetric.tss) is None


# ── _period_has_reset ──────────────────────────────────────────────────────────

def _milestone_updated(dt: datetime) -> Milestone:
    m = Milestone()
    m.period = ProgressPeriod.week
    m.updated_at = dt
    return m


def test_no_reset_same_week():
    # Monday
    monday = datetime(2026, 5, 25, 8, 0, 0, tzinfo=timezone.utc)
    wednesday = datetime(2026, 5, 27, 9, 0, 0, tzinfo=timezone.utc)
    m = _milestone_updated(monday)
    assert _period_has_reset(m, wednesday) is False


def test_reset_next_week():
    friday = datetime(2026, 5, 22, 8, 0, 0, tzinfo=timezone.utc)
    next_monday = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)
    m = _milestone_updated(friday)
    assert _period_has_reset(m, next_monday) is True


def test_no_reset_lifetime():
    m = Milestone()
    m.period = ProgressPeriod.lifetime
    m.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _period_has_reset(m, datetime(2026, 12, 31, tzinfo=timezone.utc)) is False


def test_reset_new_month():
    last_month = datetime(2026, 4, 30, 8, 0, 0, tzinfo=timezone.utc)
    this_month = datetime(2026, 5, 1, 9, 0, 0, tzinfo=timezone.utc)
    m = Milestone()
    m.period = ProgressPeriod.month
    m.updated_at = last_month
    assert _period_has_reset(m, this_month) is True


def test_no_reset_same_month():
    m = Milestone()
    m.period = ProgressPeriod.month
    m.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert _period_has_reset(m, datetime(2026, 5, 15, tzinfo=timezone.utc)) is False


# ── process_activity — cumulative ──────────────────────────────────────────────

def test_cumulative_increments_current_value(test_db):
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id, target_value=45.0, current_value=10.0)

    updates = process_activity(test_db, _run_activity(distance_km=8.2))

    assert len(updates) == 1
    assert updates[0].current_value == pytest.approx(18.2)
    assert updates[0].achieved is False
    test_db.refresh(m)
    assert m.current_value == pytest.approx(18.2)


def test_cumulative_achieves_when_target_reached(test_db):
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id, target_value=45.0, current_value=40.0)

    updates = process_activity(test_db, _run_activity(distance_km=6.0))

    assert updates[0].achieved is True
    test_db.refresh(m)
    assert m.state == MilestoneState.achieved
    assert m.achieved_at is not None


def test_cumulative_exact_target_achieves(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id, target_value=10.0, current_value=0.0)

    updates = process_activity(test_db, _run_activity(distance_km=10.0))

    assert updates[0].achieved is True


def test_cumulative_period_reset_on_new_week(test_db):
    last_friday = datetime(2026, 5, 22, 10, 0, 0, tzinfo=timezone.utc)
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id, target_value=45.0, current_value=30.0, updated_at=last_friday)

    this_monday = datetime(2026, 5, 25, 9, 0, 0, tzinfo=timezone.utc)
    updates = process_activity(test_db, _run_activity(distance_km=8.0, ts=this_monday))

    assert updates[0].current_value == pytest.approx(8.0)
    test_db.refresh(m)
    assert m.current_value == pytest.approx(8.0)


def test_cumulative_no_reset_same_week(test_db):
    this_monday = datetime(2026, 5, 25, 8, 0, 0, tzinfo=timezone.utc)
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id, target_value=45.0, current_value=20.0, updated_at=this_monday)

    wednesday = datetime(2026, 5, 27, 9, 0, 0, tzinfo=timezone.utc)
    updates = process_activity(test_db, _run_activity(distance_km=8.0, ts=wednesday))

    assert updates[0].current_value == pytest.approx(28.0)


# ── process_activity — single_effort ──────────────────────────────────────────

def test_single_effort_does_not_accumulate(test_db):
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id,
                        progress_type=ProgressType.single_effort,
                        target_value=18.0,
                        period=ProgressPeriod.lifetime,
                        current_value=0.0)

    process_activity(test_db, _run_activity(distance_km=14.0))
    process_activity(test_db, _run_activity(distance_km=14.0))

    test_db.refresh(m)
    assert m.current_value == pytest.approx(14.0)  # not 28.0


def test_single_effort_achieves_on_meeting_target(test_db):
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id,
                        progress_type=ProgressType.single_effort,
                        target_value=18.0,
                        period=ProgressPeriod.lifetime,
                        current_value=0.0)

    updates = process_activity(test_db, _run_activity(distance_km=18.5))

    assert updates[0].achieved is True
    test_db.refresh(m)
    assert m.state == MilestoneState.achieved
    assert m.achieved_at is not None


def test_single_effort_tracks_best_value(test_db):
    g = _make_goal(test_db)
    m = _make_milestone(test_db, g.id,
                        progress_type=ProgressType.single_effort,
                        target_value=18.0,
                        period=ProgressPeriod.lifetime,
                        current_value=12.0)

    # Better run
    process_activity(test_db, _run_activity(distance_km=15.0))
    test_db.refresh(m)
    assert m.current_value == pytest.approx(15.0)

    # Shorter run does not decrease best
    process_activity(test_db, _run_activity(distance_km=10.0))
    test_db.refresh(m)
    assert m.current_value == pytest.approx(15.0)


# ── process_activity — filtering ──────────────────────────────────────────────

def test_wrong_activity_type_skipped(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id, activity_type="run")

    ride = {**_run_activity(), "activity_type": "Ride"}
    updates = process_activity(test_db, ride)

    assert updates == []


def test_any_activity_type_matches_all(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id, activity_type="any")

    ride = {**_run_activity(), "activity_type": "Ride"}
    updates = process_activity(test_db, ride)

    assert len(updates) == 1


def test_already_achieved_milestone_skipped(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id, state=MilestoneState.achieved, current_value=45.0)

    updates = process_activity(test_db, _run_activity())

    assert updates == []


def test_no_progress_type_milestone_skipped(test_db):
    g = _make_goal(test_db)
    m = Milestone(
        goal_id=g.id,
        title="Date-based milestone",
        state=MilestoneState.pending,
        sequence=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_db.add(m)
    test_db.commit()

    updates = process_activity(test_db, _run_activity())

    assert updates == []


def test_missing_metric_value_skipped(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id, metric=ProgressMetric.tss, target_value=80.0)

    # Activity has no TSS
    updates = process_activity(test_db, _run_activity(tss=None))

    assert updates == []


# ── activity_dict_from_row ─────────────────────────────────────────────────────

def test_activity_dict_from_row_parses_notes():
    import json
    from unittest.mock import MagicMock
    from app.models.metric_reading import MetricType

    row = MagicMock()
    row.notes = json.dumps({
        "type": "Run",
        "distance_km": 10.2,
        "moving_time_s": 3600,
        "tss": None,
    })
    row.text_value = "Run"
    row.value = 10.2
    row.timestamp = _now()
    row.metric_type = MetricType.activity

    result = activity_dict_from_row(row)

    assert result["activity_type"] == "Run"
    assert result["distance_km"] == 10.2
    assert result["moving_time_s"] == 3600


def test_activity_dict_from_row_fallback_on_bad_notes():
    from unittest.mock import MagicMock
    from app.models.metric_reading import MetricType

    row = MagicMock()
    row.notes = "not json"
    row.text_value = "Ride"
    row.value = 25.0
    row.timestamp = _now()
    row.metric_type = MetricType.activity

    result = activity_dict_from_row(row)

    assert result["activity_type"] == "Ride"


# ── duration metric ────────────────────────────────────────────────────────────

def test_cumulative_duration_min(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id,
                    metric=ProgressMetric.duration_min,
                    target_value=60.0,
                    current_value=0.0)

    updates = process_activity(test_db, _run_activity(moving_time_s=1800))  # 30 min

    assert updates[0].current_value == pytest.approx(30.0)
    assert updates[0].achieved is False


def test_cumulative_count(test_db):
    g = _make_goal(test_db)
    _make_milestone(test_db, g.id,
                    metric=ProgressMetric.count,
                    target_value=3.0,
                    current_value=2.0)

    updates = process_activity(test_db, _run_activity())

    assert updates[0].achieved is True
