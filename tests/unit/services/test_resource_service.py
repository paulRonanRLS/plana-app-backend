"""Unit tests for app/services/resource.py.

Uses the SQLite in-memory test_db fixture.

MetricReading has a composite PK (id, timestamp) — SQLite has no sequence, so
tests provide explicit id values via the _next_id() helper which resets each test.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models.goal import Goal, GoalState
from app.models.metric_reading import MetricReading, MetricType, MetricSource
from app.models.milestone import Milestone, MilestoneState
from app.models.resource_profile import ResourceProfile
from app.models.sacrifice import Sacrifice, ResourceType
from app.services import resource as svc


# ── Test helpers ───────────────────────────────────────────────────────────────

_metric_id = 0


@pytest.fixture(autouse=True)
def reset_metric_id():
    global _metric_id
    _metric_id = 0
    yield


def _next_id() -> int:
    global _metric_id
    _metric_id += 1
    return _metric_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def make_goal(
    db,
    title="Test goal",
    state=GoalState.active,
    weekly_time_hours: float | None = None,
    weekly_tss: float | None = None,
) -> Goal:
    now = _now()
    g = Goal(
        title=title,
        state=state,
        weekly_time_hours=weekly_time_hours,
        weekly_tss=weekly_tss,
        created_at=now,
        updated_at=now,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def make_milestone(
    db,
    goal_id: int,
    state: MilestoneState = MilestoneState.active,
    title: str = "Milestone",
) -> Milestone:
    now = _now()
    m = Milestone(
        goal_id=goal_id,
        title=title,
        state=state,
        sequence=0,
        created_at=now,
        updated_at=now,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def make_metric(
    db,
    metric_type: MetricType,
    value: float | None = None,
    text_value: str | None = None,
    timestamp: datetime | None = None,
    source: MetricSource = MetricSource.manual,
) -> MetricReading:
    if timestamp is None:
        timestamp = _now()
    r = MetricReading(
        id=_next_id(),
        timestamp=timestamp,
        metric_type=metric_type,
        value=value,
        text_value=text_value,
        source=source,
    )
    db.add(r)
    db.commit()
    return r


def make_sacrifice(
    db,
    goal_id: int,
    resource: ResourceType = ResourceType.time,
    days_ago: int = 0,
) -> Sacrifice:
    s = Sacrifice(
        goal_id=goal_id,
        date=date.today() - timedelta(days=days_ago),
        resource=resource,
        created_at=_now(),
    )
    db.add(s)
    db.commit()
    return s


def make_profile(
    db,
    week_start: date | None = None,
    time_envelope: float = 62.0,
    tss_envelope: float = 320.0,
    sleep_hours: float | None = None,
    work_hours: float | None = None,
) -> ResourceProfile:
    if week_start is None:
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
    now = _now()
    p = ResourceProfile(
        week_start=week_start,
        time_envelope_hours=time_envelope,
        recovery_envelope_tss=tss_envelope,
        sleep_hours_per_night=sleep_hours,
        work_hours_per_week=work_hours,
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def this_week_start() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


def ts_in_week(week_start: date, day_offset: int = 0) -> datetime:
    """Return a UTC datetime inside the given week."""
    d = week_start + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, 10, 0, tzinfo=timezone.utc)


# ── Pure calculations ──────────────────────────────────────────────────────────

def test_time_envelope_spec_default():
    # Spec: 168 - (8 * 7) - 50 = 62
    assert svc.calculate_time_envelope(8.0, 50.0) == pytest.approx(62.0)


def test_time_envelope_short_sleep():
    # 168 - (6 * 7) - 40 = 168 - 42 - 40 = 86
    assert svc.calculate_time_envelope(6.0, 40.0) == pytest.approx(86.0)


def test_time_envelope_heavy_work():
    # 168 - (8 * 7) - 80 = 168 - 56 - 80 = 32
    assert svc.calculate_time_envelope(8.0, 80.0) == pytest.approx(32.0)


def test_time_envelope_zero_work():
    assert svc.calculate_time_envelope(7.0, 0.0) == pytest.approx(168.0 - 49.0)


def test_time_envelope_fractional_sleep():
    # 7.5h sleep, 45h work → 168 - 52.5 - 45 = 70.5
    assert svc.calculate_time_envelope(7.5, 45.0) == pytest.approx(70.5)


# ── TSS baseline ───────────────────────────────────────────────────────────────

def test_tss_baseline_no_data_returns_default(test_db):
    assert svc.get_tss_baseline(test_db) == pytest.approx(320.0)


def test_tss_baseline_with_data(test_db):
    # 9 activities × 70 TSS each over 90 days → avg weekly = 630 / (90/7) ≈ 49
    for i in range(9):
        ts = _now() - timedelta(days=i * 10)
        make_metric(test_db, MetricType.tss, value=70.0, timestamp=ts)
    result = svc.get_tss_baseline(test_db, days=90)
    expected = 630.0 / (90.0 / 7.0)
    assert result == pytest.approx(expected, rel=1e-6)


def test_tss_baseline_custom_window(test_db):
    # Reading 5 days ago — inside 30-day window, outside 3-day window
    ts = _now() - timedelta(days=5)
    make_metric(test_db, MetricType.tss, value=100.0, timestamp=ts)
    assert svc.get_tss_baseline(test_db, days=30) == pytest.approx(100.0 / (30.0 / 7.0))
    assert svc.get_tss_baseline(test_db, days=3) == pytest.approx(320.0)  # outside window


def test_tss_baseline_ignores_other_metrics(test_db):
    make_metric(test_db, MetricType.hrv, value=50.0)
    make_metric(test_db, MetricType.sleep_score, value=80.0)
    assert svc.get_tss_baseline(test_db) == pytest.approx(320.0)


def test_tss_baseline_ignores_null_values(test_db):
    make_metric(test_db, MetricType.tss, value=None)   # null value, should be excluded
    make_metric(test_db, MetricType.tss, value=140.0)
    result = svc.get_tss_baseline(test_db, days=90)
    assert result == pytest.approx(140.0 / (90.0 / 7.0))


# ── Attention count ────────────────────────────────────────────────────────────

def test_attention_count_empty(test_db):
    assert svc.get_attention_count(test_db) == 0


def test_attention_count_active_milestones(test_db):
    g = make_goal(test_db)
    make_milestone(test_db, g.id, state=MilestoneState.active)
    make_milestone(test_db, g.id, state=MilestoneState.pending)
    assert svc.get_attention_count(test_db) == 2


def test_attention_count_excludes_achieved_and_missed(test_db):
    g = make_goal(test_db)
    make_milestone(test_db, g.id, state=MilestoneState.active)
    make_milestone(test_db, g.id, state=MilestoneState.achieved)
    make_milestone(test_db, g.id, state=MilestoneState.missed)
    assert svc.get_attention_count(test_db) == 1


def test_attention_count_excludes_terminal_goal_milestones(test_db):
    released = make_goal(test_db, state=GoalState.released)
    completed = make_goal(test_db, state=GoalState.completed)
    active = make_goal(test_db, state=GoalState.active)
    make_milestone(test_db, released.id, state=MilestoneState.active)
    make_milestone(test_db, completed.id, state=MilestoneState.pending)
    make_milestone(test_db, active.id, state=MilestoneState.active)
    assert svc.get_attention_count(test_db) == 1


def test_attention_count_episodes_this_week(test_db):
    week = this_week_start()
    make_metric(test_db, MetricType.physical_state, text_value="sore legs", timestamp=ts_in_week(week, 0))
    make_metric(test_db, MetricType.illness_log, text_value="cold start", timestamp=ts_in_week(week, 2))
    assert svc.get_attention_count(test_db, week_start=week) == 2


def test_attention_count_episodes_prior_week_not_counted(test_db):
    week = this_week_start()
    last = week - timedelta(weeks=1)
    make_metric(test_db, MetricType.physical_state, text_value="old niggle", timestamp=ts_in_week(last, 3))
    assert svc.get_attention_count(test_db, week_start=week) == 0


def test_attention_count_ignores_non_episode_metrics(test_db):
    week = this_week_start()
    make_metric(test_db, MetricType.hrv, value=45.0, timestamp=ts_in_week(week, 0))
    make_metric(test_db, MetricType.tss, value=120.0, timestamp=ts_in_week(week, 1))
    assert svc.get_attention_count(test_db, week_start=week) == 0


def test_attention_count_combines_milestones_and_episodes(test_db):
    week = this_week_start()
    g = make_goal(test_db)
    make_milestone(test_db, g.id, state=MilestoneState.pending)
    make_metric(test_db, MetricType.physical_state, text_value="knee twinge", timestamp=ts_in_week(week, 1))
    assert svc.get_attention_count(test_db, week_start=week) == 2


# ── Tension scoring ────────────────────────────────────────────────────────────

def test_tension_no_goals(test_db):
    t = svc.get_resource_tension(test_db)
    assert t.total_committed_time_hours == 0.0
    assert t.total_committed_tss == 0.0
    assert t.time_ratio == pytest.approx(0.0)
    assert t.recovery_ratio == pytest.approx(0.0)
    assert t.goals == []


def test_tension_undercommitted(test_db):
    make_profile(test_db, time_envelope=62.0, tss_envelope=320.0)
    make_goal(test_db, weekly_time_hours=10.0, weekly_tss=80.0)
    t = svc.get_resource_tension(test_db)
    assert t.time_ratio == pytest.approx(10.0 / 62.0)
    assert t.recovery_ratio == pytest.approx(80.0 / 320.0)
    assert t.time_ratio < 1.0
    assert t.recovery_ratio < 1.0


def test_tension_overcommitted(test_db):
    make_profile(test_db, time_envelope=62.0, tss_envelope=320.0)
    make_goal(test_db, title="A", weekly_time_hours=40.0, weekly_tss=200.0)
    make_goal(test_db, title="B", weekly_time_hours=30.0, weekly_tss=150.0)
    t = svc.get_resource_tension(test_db)
    assert t.time_ratio == pytest.approx(70.0 / 62.0)
    assert t.time_ratio > 1.0
    assert t.total_committed_time_hours == pytest.approx(70.0)
    assert t.total_committed_tss == pytest.approx(350.0)


def test_tension_goal_time_shares_sum_to_one(test_db):
    make_goal(test_db, title="A", weekly_time_hours=8.0)
    make_goal(test_db, title="B", weekly_time_hours=4.0)
    make_goal(test_db, title="C", weekly_time_hours=12.0)
    t = svc.get_resource_tension(test_db)
    total_share = sum(g.time_share for g in t.goals)
    assert total_share == pytest.approx(1.0)


def test_tension_tss_shares_sum_to_one(test_db):
    make_goal(test_db, title="A", weekly_tss=100.0)
    make_goal(test_db, title="B", weekly_tss=220.0)
    t = svc.get_resource_tension(test_db)
    total_share = sum(g.tss_share for g in t.goals)
    assert total_share == pytest.approx(1.0)


def test_tension_goals_sorted_by_time_share_desc(test_db):
    make_goal(test_db, title="Small", weekly_time_hours=4.0)
    make_goal(test_db, title="Large", weekly_time_hours=20.0)
    make_goal(test_db, title="Medium", weekly_time_hours=10.0)
    t = svc.get_resource_tension(test_db)
    shares = [g.time_share for g in t.goals]
    assert shares == sorted(shares, reverse=True)


def test_tension_excludes_terminal_goals(test_db):
    make_goal(test_db, title="Active", state=GoalState.active, weekly_time_hours=10.0)
    make_goal(test_db, title="Done", state=GoalState.completed, weekly_time_hours=20.0)
    make_goal(test_db, title="Gone", state=GoalState.released, weekly_time_hours=30.0)
    t = svc.get_resource_tension(test_db)
    assert t.total_committed_time_hours == pytest.approx(10.0)
    assert len(t.goals) == 1


def test_tension_null_allocations_treated_as_zero(test_db):
    make_goal(test_db, title="No alloc")   # no time/tss set
    t = svc.get_resource_tension(test_db)
    assert t.total_committed_time_hours == 0.0
    assert t.goals[0].time_share == 0.0


def test_tension_uses_profile_envelope(test_db):
    make_profile(test_db, time_envelope=50.0, tss_envelope=200.0)
    make_goal(test_db, weekly_time_hours=25.0, weekly_tss=100.0)
    t = svc.get_resource_tension(test_db)
    assert t.time_envelope_hours == pytest.approx(50.0)
    assert t.time_ratio == pytest.approx(25.0 / 50.0)


def test_tension_falls_back_to_defaults_without_profile(test_db):
    make_goal(test_db, weekly_time_hours=10.0, weekly_tss=50.0)
    t = svc.get_resource_tension(test_db)
    assert t.time_envelope_hours == pytest.approx(62.0)
    assert t.recovery_envelope_tss == pytest.approx(320.0)


def test_tension_primacy_goal_visible_in_goals_list(test_db):
    make_goal(test_db, title="Top goal", state=GoalState.primacy, weekly_time_hours=15.0)
    make_goal(test_db, title="Sub goal", state=GoalState.subordinate, weekly_time_hours=5.0)
    t = svc.get_resource_tension(test_db)
    states = {g.goal_state for g in t.goals}
    assert "primacy" in states
    assert "subordinate" in states


# ── Willpower pattern ──────────────────────────────────────────────────────────

def test_willpower_no_sacrifices(test_db):
    w = svc.get_willpower_pattern(test_db)
    assert w.sacrifice_count_28d == 0
    assert w.dominant_resource is None
    assert all(v == 0 for v in w.by_resource.values())


def test_willpower_counts_by_resource(test_db):
    g = make_goal(test_db)
    make_sacrifice(test_db, g.id, resource=ResourceType.time)
    make_sacrifice(test_db, g.id, resource=ResourceType.time)
    make_sacrifice(test_db, g.id, resource=ResourceType.recovery)
    w = svc.get_willpower_pattern(test_db)
    assert w.sacrifice_count_28d == 3
    assert w.by_resource["time"] == 2
    assert w.by_resource["recovery"] == 1


def test_willpower_all_resource_keys_present(test_db):
    w = svc.get_willpower_pattern(test_db)
    assert set(w.by_resource.keys()) == {"time", "recovery", "attention", "willpower"}


def test_willpower_dominant_resource(test_db):
    g = make_goal(test_db)
    make_sacrifice(test_db, g.id, resource=ResourceType.attention)
    make_sacrifice(test_db, g.id, resource=ResourceType.attention)
    make_sacrifice(test_db, g.id, resource=ResourceType.recovery)
    w = svc.get_willpower_pattern(test_db)
    assert w.dominant_resource == "attention"


def test_willpower_excludes_old_sacrifices(test_db):
    g = make_goal(test_db)
    make_sacrifice(test_db, g.id, resource=ResourceType.time, days_ago=5)    # inside window
    make_sacrifice(test_db, g.id, resource=ResourceType.time, days_ago=30)   # on boundary
    make_sacrifice(test_db, g.id, resource=ResourceType.time, days_ago=60)   # outside
    w = svc.get_willpower_pattern(test_db, days=28)
    # days_ago=30 is on or outside the boundary: date.today() - 28 days = cutoff
    # sacrifice at days_ago=30 has date = today - 30, which is < today - 28 → excluded
    assert w.sacrifice_count_28d == 1
    assert w.by_resource["time"] == 1


def test_willpower_custom_window(test_db):
    g = make_goal(test_db)
    make_sacrifice(test_db, g.id, resource=ResourceType.willpower, days_ago=3)
    make_sacrifice(test_db, g.id, resource=ResourceType.willpower, days_ago=10)
    assert svc.get_willpower_pattern(test_db, days=7).sacrifice_count_28d == 1
    assert svc.get_willpower_pattern(test_db, days=14).sacrifice_count_28d == 2


# ── Week snapshot ──────────────────────────────────────────────────────────────

def test_week_snapshot_defaults_without_profile(test_db):
    week = this_week_start()
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.time_envelope_hours == pytest.approx(62.0)
    assert snap.recovery_envelope_tss == pytest.approx(320.0)
    assert snap.label == "this_week"
    assert snap.week_start == week


def test_week_snapshot_uses_profile_envelope(test_db):
    week = this_week_start()
    make_profile(test_db, week_start=week, time_envelope=55.0, tss_envelope=280.0)
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.time_envelope_hours == pytest.approx(55.0)
    assert snap.recovery_envelope_tss == pytest.approx(280.0)


def test_week_snapshot_committed_from_goals(test_db):
    week = this_week_start()
    make_goal(test_db, weekly_time_hours=8.0, weekly_tss=100.0)
    make_goal(test_db, weekly_time_hours=5.0, weekly_tss=60.0)
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.time_committed_hours == pytest.approx(13.0)
    assert snap.recovery_committed_tss == pytest.approx(160.0)
    assert snap.goal_count == 2


def test_week_snapshot_actual_tss_from_readings(test_db):
    week = this_week_start()
    make_metric(test_db, MetricType.tss, value=90.0, timestamp=ts_in_week(week, 0))
    make_metric(test_db, MetricType.tss, value=60.0, timestamp=ts_in_week(week, 2))
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.recovery_actual_tss == pytest.approx(150.0)


def test_week_snapshot_no_tss_readings_gives_none(test_db):
    week = this_week_start()
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.recovery_actual_tss is None


def test_week_snapshot_tss_scoped_to_week(test_db):
    week = this_week_start()
    last = week - timedelta(weeks=1)
    make_metric(test_db, MetricType.tss, value=200.0, timestamp=ts_in_week(week, 1))
    make_metric(test_db, MetricType.tss, value=999.0, timestamp=ts_in_week(last, 3))  # prior week
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.recovery_actual_tss == pytest.approx(200.0)


def test_week_snapshot_time_actual_is_none(test_db):
    # Time actuals not tracked until Garmin/Strava ingestion (tasks 7/8)
    week = this_week_start()
    snap = svc.get_week_snapshot(test_db, week, "this_week")
    assert snap.time_actual_hours is None


# ── Three week view ────────────────────────────────────────────────────────────

def test_three_week_view_has_correct_labels(test_db):
    view = svc.get_three_week_view(test_db, reference_date=date.today())
    assert view.last_week.label == "last_week"
    assert view.this_week.label == "this_week"
    assert view.next_week.label == "next_week"


def test_three_week_view_correct_week_starts(test_db):
    ref = date(2026, 5, 20)          # a Wednesday
    view = svc.get_three_week_view(test_db, reference_date=ref)
    assert view.this_week.week_start == date(2026, 5, 18)   # Monday
    assert view.last_week.week_start == date(2026, 5, 11)
    assert view.next_week.week_start == date(2026, 5, 25)


def test_three_week_view_last_week_has_tss_actuals(test_db):
    ref = date(2026, 5, 20)
    last_week_start = date(2026, 5, 11)
    make_metric(
        test_db,
        MetricType.tss,
        value=130.0,
        timestamp=ts_in_week(last_week_start, 2),
    )
    view = svc.get_three_week_view(test_db, reference_date=ref)
    assert view.last_week.recovery_actual_tss == pytest.approx(130.0)
    assert view.this_week.recovery_actual_tss is None
    assert view.next_week.recovery_actual_tss is None


def test_three_week_view_committed_same_for_all_weeks(test_db):
    make_goal(test_db, weekly_time_hours=10.0, weekly_tss=80.0)
    view = svc.get_three_week_view(test_db)
    assert view.last_week.time_committed_hours == pytest.approx(10.0)
    assert view.this_week.time_committed_hours == pytest.approx(10.0)
    assert view.next_week.time_committed_hours == pytest.approx(10.0)


def test_three_week_view_separate_profiles_per_week(test_db):
    ref = date(2026, 5, 20)
    last_week_start = date(2026, 5, 11)
    this_week_start_d = date(2026, 5, 18)
    make_profile(test_db, week_start=last_week_start, time_envelope=60.0)
    make_profile(test_db, week_start=this_week_start_d, time_envelope=55.0)
    view = svc.get_three_week_view(test_db, reference_date=ref)
    assert view.last_week.time_envelope_hours == pytest.approx(60.0)
    assert view.this_week.time_envelope_hours == pytest.approx(55.0)
    assert view.next_week.time_envelope_hours == pytest.approx(62.0)  # no profile → default


def test_three_week_view_goal_count_consistent(test_db):
    make_goal(test_db, title="A")
    make_goal(test_db, title="B")
    make_goal(test_db, state=GoalState.completed)   # terminal — excluded
    view = svc.get_three_week_view(test_db)
    assert view.last_week.goal_count == 2
    assert view.this_week.goal_count == 2
    assert view.next_week.goal_count == 2
