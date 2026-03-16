"""
Unit tests for user service.

Tests business logic functions without HTTP layer.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.user import User
from app.services import user_service


def test_get_by_id_found(test_db: Session, test_user):
    """Test get_by_id returns user when exists."""
    user = test_user["user"]

    result = user_service.get_by_id(test_db, user.id)

    assert result is not None
    assert result.id == user.id
    assert result.email == user.email
    assert result.name == user.name


def test_get_by_id_not_found(test_db: Session):
    """Test get_by_id returns None when user doesn't exist."""
    result = user_service.get_by_id(test_db, "usr_nonexistent")

    assert result is None


def test_update_user_partial(test_db: Session, test_user):
    """Test update only modifies provided fields."""
    user = test_user["user"]
    original_email = user.email
    original_name = user.name

    # Update only preferred_units
    update_data = {"preferred_units": "imperial"}
    updated = user_service.update(test_db, user, update_data)

    assert updated.preferred_units == "imperial"
    assert updated.email == original_email  # Unchanged
    assert updated.name == original_name  # Unchanged
    assert updated.default_servings == 4  # Unchanged


def test_update_user_excludes_unset(test_db: Session, test_user):
    """Test that omitting fields doesn't null them out."""
    user = test_user["user"]
    original_servings = user.default_servings

    # Update name only, don't send default_servings
    update_data = {"name": "Updated Name"}
    updated = user_service.update(test_db, user, update_data)

    assert updated.name == "Updated Name"
    assert updated.default_servings == original_servings  # Not changed


def test_update_user_multiple_fields(test_db: Session, test_user):
    """Test updating multiple fields at once."""
    user = test_user["user"]

    update_data = {
        "name": "New Name",
        "preferred_units": "imperial",
        "default_servings": 6,
        "voice_enabled": False,
    }
    updated = user_service.update(test_db, user, update_data)

    assert updated.name == "New Name"
    assert updated.preferred_units == "imperial"
    assert updated.default_servings == 6
    assert updated.voice_enabled is False


def test_delete_user(test_db: Session, test_user):
    """Test user is removed from database after delete."""
    user = test_user["user"]
    user_id = user.id

    # Delete user
    user_service.delete(test_db, user)

    # Verify user no longer exists
    result = test_db.query(User).filter(User.id == user_id).first()
    assert result is None
