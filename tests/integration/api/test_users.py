"""
Integration tests for user router.

Tests the HTTP endpoints end-to-end with test database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.user import User


def test_get_me_returns_current_user(test_user):
    """Test GET /users/me returns authenticated user's profile."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    response = client.get("/v1/users/me", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user.id
    assert data["email"] == user.email
    assert data["name"] == user.name
    assert data["preferred_units"] == "metric"
    assert data["default_servings"] == 4
    assert data["voice_enabled"] is True


def test_get_me_auto_creates_user(test_user):
    """Test GET /users/me creates user on first request with new UID."""
    client = test_user["client"]

    # Use a new UID that doesn't exist in DB yet
    new_headers = {"Authorization": "Bearer new-user-uid-999"}

    # Make request with new UID (auth stub will auto-create)
    response = client.get("/v1/users/me", headers=new_headers)

    assert response.status_code == 200
    data = response.json()
    # Auth stub auto-creates user with UID-based defaults
    # Check that user was created (email/name will contain parts of the UID)
    assert "new-user" in data["email"] or "new-user" in data["name"]
    # Verify it's a valid user response
    assert "id" in data
    assert "email" in data


def test_patch_me_partial_update(test_user):
    """Test PATCH /users/me updates only sent fields."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Update only preferred_units
    update_data = {"preferred_units": "imperial"}
    response = client.patch("/v1/users/me", headers=headers, json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["preferred_units"] == "imperial"
    assert data["email"] == user.email  # Unchanged
    assert data["name"] == user.name  # Unchanged
    assert data["default_servings"] == 4  # Unchanged


def test_patch_me_excludes_unset(test_user):
    """Test omitted fields remain unchanged."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Update name only
    update_data = {"name": "Updated Name"}
    response = client.patch("/v1/users/me", headers=headers, json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["preferred_units"] == user.preferred_units  # Unchanged
    assert data["default_servings"] == user.default_servings  # Unchanged


def test_patch_me_multiple_fields(test_user):
    """Test updating multiple fields at once."""
    client = test_user["client"]
    headers = test_user["headers"]

    update_data = {
        "name": "New Name",
        "preferred_units": "imperial",
        "default_servings": 6,
        "voice_enabled": False,
    }
    response = client.patch("/v1/users/me", headers=headers, json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Name"
    assert data["preferred_units"] == "imperial"
    assert data["default_servings"] == 6
    assert data["voice_enabled"] is False


def test_delete_me(test_user):
    """Test DELETE /users/me deletes user and returns 204."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Delete user
    response = client.delete("/v1/users/me", headers=headers)

    assert response.status_code == 204
    assert response.content == b""  # No content in response

    # Try to get user again - should fail or auto-create new one
    response2 = client.get("/v1/users/me", headers=headers)
    # After delete, auth stub will auto-create a new user with same UID
    assert response2.status_code == 200


def test_unauthenticated_request(test_user):
    """Test requests without Authorization header return 401."""
    client = test_user["client"]

    # No headers - should be rejected
    response = client.get("/v1/users/me")

    assert response.status_code == 401
    assert "detail" in response.json()


def test_invalid_auth_header(test_user):
    """Test malformed Authorization header returns 401."""
    client = test_user["client"]

    # Invalid format (missing Bearer prefix)
    headers = {"Authorization": "InvalidTokenFormat"}
    response = client.get("/v1/users/me", headers=headers)

    assert response.status_code == 401
    assert "detail" in response.json()
