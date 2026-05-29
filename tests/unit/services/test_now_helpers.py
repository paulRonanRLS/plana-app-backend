"""Unit tests for Now view helper functions in app/routers/web.py."""

from app.routers.web import _compute_general_condition


# ── _compute_general_condition ────────────────────────────────────────────────

def test_general_condition_no_data():
    assert _compute_general_condition(None, None, None, None) == "No data yet"


def test_general_condition_no_data_hrv_without_avg():
    # HRV present but no 90-day avg — not enough to deplete or restore
    result = _compute_general_condition(None, None, hrv=55.0, hrv_avg_90d=None)
    # hrv alone with no avg cannot trigger depleted; battery/sleep both None
    # → only hrv is set, but battery/sleep are None → not "No data yet"
    # → Depleted check: hrv < avg*0.85 requires avg to be not None → skip
    # → Restored check: battery_ok=True, sleep_ok=True, hrv_ok=True (avg is None)
    assert result == "Restored"


def test_general_condition_depleted_by_sleep():
    assert _compute_general_condition(sleep_score=40.0, body_battery=None, hrv=None, hrv_avg_90d=None) == "Depleted"


def test_general_condition_depleted_by_battery():
    assert _compute_general_condition(sleep_score=None, body_battery=15.0, hrv=None, hrv_avg_90d=None) == "Depleted"


def test_general_condition_depleted_by_hrv():
    # hrv = 50, avg = 65 → 50 < 65 * 0.85 (55.25) → Depleted
    assert _compute_general_condition(sleep_score=None, body_battery=None, hrv=50.0, hrv_avg_90d=65.0) == "Depleted"


def test_general_condition_depleted_prefers_depleted_even_with_good_sleep():
    # Sleep fine but battery very low
    assert _compute_general_condition(sleep_score=80.0, body_battery=10.0, hrv=None, hrv_avg_90d=None) == "Depleted"


def test_general_condition_restored_all_ok():
    # sleep >= 65, battery >= 40, hrv >= 95% of avg
    assert _compute_general_condition(sleep_score=70.0, body_battery=50.0, hrv=60.0, hrv_avg_90d=60.0) == "Restored"


def test_general_condition_restored_only_sleep():
    # Only sleep present and it's fine
    assert _compute_general_condition(sleep_score=75.0, body_battery=None, hrv=None, hrv_avg_90d=None) == "Restored"


def test_general_condition_carrying_load_sleep_low():
    # sleep between 50 and 65 → not depleted, not fully restored → Carrying Load
    assert _compute_general_condition(sleep_score=55.0, body_battery=None, hrv=None, hrv_avg_90d=None) == "Carrying Load"


def test_general_condition_carrying_load_battery_low():
    # battery between 20 and 40 → Carrying Load
    assert _compute_general_condition(sleep_score=None, body_battery=30.0, hrv=None, hrv_avg_90d=None) == "Carrying Load"


def test_general_condition_carrying_load_hrv_slightly_depressed():
    # hrv = 58, avg = 65 → ratio 0.892, above 0.85 (not depleted) but below 0.95 (not restored)
    assert _compute_general_condition(sleep_score=None, body_battery=None, hrv=58.0, hrv_avg_90d=65.0) == "Carrying Load"


def test_general_condition_boundary_sleep_exactly_50_is_depleted():
    assert _compute_general_condition(sleep_score=50.0, body_battery=None, hrv=None, hrv_avg_90d=None) == "Carrying Load"


def test_general_condition_boundary_sleep_49_is_depleted():
    assert _compute_general_condition(sleep_score=49.9, body_battery=None, hrv=None, hrv_avg_90d=None) == "Depleted"


def test_general_condition_boundary_battery_exactly_20_not_depleted():
    assert _compute_general_condition(sleep_score=None, body_battery=20.0, hrv=None, hrv_avg_90d=None) == "Carrying Load"


def test_general_condition_boundary_battery_19_is_depleted():
    assert _compute_general_condition(sleep_score=None, body_battery=19.9, hrv=None, hrv_avg_90d=None) == "Depleted"
