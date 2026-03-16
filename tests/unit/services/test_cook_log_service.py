"""
Unit tests for cook log service business logic.
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException

from app.services import cook_log_service
from app.models.cook_log import CookLog
from app.models.recipe import Recipe


def test_create_cook_log_for_own_recipe(test_user, test_recipe, test_db):
    """Test creating a cook log for user's own recipe."""
    user = test_user["user"]

    data = {
        "cooked_at": datetime.now(timezone.utc),
        "servings_made": 4,
        "rating": 5,
        "notes": "Delicious!",
    }

    cook_log = cook_log_service.create(test_db, user, test_recipe.id, data)

    assert cook_log.id is not None
    assert cook_log.recipe_id == test_recipe.id
    assert cook_log.user_id == user.id
    assert cook_log.servings_made == 4
    assert cook_log.rating == 5
    assert cook_log.notes == "Delicious!"


def test_create_cook_log_for_foreign_recipe_raises_404(test_user, test_other_user, test_db):
    """Test creating a cook log for recipe owned by another user raises 404."""
    user = test_user["user"]
    other = test_other_user["user"]

    # Create recipe owned by other user
    recipe = Recipe(
        owner_id=other.id,
        title="Other's Recipe",
        source_type="manual",
        base_servings=2,
    )
    test_db.add(recipe)
    test_db.commit()

    data = {
        "cooked_at": datetime.now(timezone.utc),
        "servings_made": 2,
        "rating": 4,
    }

    # Should raise 404 because user doesn't own the recipe
    with pytest.raises(HTTPException) as exc_info:
        cook_log_service.create(test_db, user, recipe.id, data)

    assert exc_info.value.status_code == 404


def test_list_for_recipe_ordered_newest_first(test_user, test_recipe, test_db):
    """Test listing cook logs for a recipe returns them ordered newest first."""
    user = test_user["user"]

    # Create 3 cook logs with different dates
    now = datetime.now(timezone.utc)

    log1 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=2),
        servings_made=4,
        rating=4,
    )
    log2 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=1),
        servings_made=4,
        rating=5,
    )
    log3 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now,
        servings_made=4,
        rating=3,
    )

    test_db.add_all([log1, log2, log3])
    test_db.commit()

    # List logs
    logs = cook_log_service.list_for_recipe(test_db, user, test_recipe.id)

    # Should be ordered newest first
    assert len(logs) == 3
    assert logs[0].id == log3.id
    assert logs[1].id == log2.id
    assert logs[2].id == log1.id


def test_list_for_user_date_filter(test_user, test_db):
    """Test listing cook logs for user with date filters."""
    user = test_user["user"]

    # Create 2 recipes
    recipe1 = Recipe(owner_id=user.id, title="Recipe 1", source_type="manual", base_servings=4)
    recipe2 = Recipe(owner_id=user.id, title="Recipe 2", source_type="manual", base_servings=4)
    test_db.add_all([recipe1, recipe2])
    test_db.commit()

    # Create cook logs across different dates
    now = datetime.now(timezone.utc)

    old_log = CookLog(
        recipe_id=recipe1.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=10),
        servings_made=4,
        rating=4,
    )
    recent_log = CookLog(
        recipe_id=recipe2.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=2),
        servings_made=4,
        rating=5,
    )
    today_log = CookLog(
        recipe_id=recipe1.id,
        user_id=user.id,
        cooked_at=now,
        servings_made=4,
        rating=3,
    )

    test_db.add_all([old_log, recent_log, today_log])
    test_db.commit()

    # Filter: last 7 days
    cutoff = now - timedelta(days=7)
    logs = cook_log_service.list_for_user(test_db, user, cooked_after=cutoff)

    # Should only get recent_log and today_log
    assert len(logs) == 2
    assert old_log.id not in [log.id for log in logs]


def test_get_stats_no_logs_returns_zeros(test_user, test_recipe, test_db):
    """Test getting stats for recipe with no logs returns zeros/nulls."""
    user = test_user["user"]

    stats = cook_log_service.get_stats_for_recipe(test_db, user, test_recipe.id)

    assert stats["times_cooked"] == 0
    assert stats["average_rating"] is None
    assert stats["last_cooked"] is None


def test_get_stats_aggregates_correctly(test_user, test_recipe, test_db):
    """Test that stats are computed using SQL aggregates."""
    user = test_user["user"]

    now = datetime.now(timezone.utc)

    # Create 3 cook logs
    log1 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=5),
        servings_made=4,
        rating=5,
    )
    log2 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=2),
        servings_made=4,
        rating=4,
    )
    log3 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now,
        servings_made=4,
        rating=3,
    )

    test_db.add_all([log1, log2, log3])
    test_db.commit()

    # Get stats
    stats = cook_log_service.get_stats_for_recipe(test_db, user, test_recipe.id)

    assert stats["times_cooked"] == 3
    assert stats["average_rating"] == 4.0  # (5 + 4 + 3) / 3
    # SQLite returns naive datetime, so compare with naive version
    now_naive = now.replace(tzinfo=None)
    assert stats["last_cooked"] == now_naive or abs((stats["last_cooked"] - now_naive).total_seconds()) < 1
