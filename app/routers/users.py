"""
User endpoints - profile management.

Provides:
- GET /users/me - Get current user profile
- PATCH /users/me - Update user preferences
- DELETE /users/me - Delete account and all data
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.schemas.user import UserResponse, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Get the current authenticated user's profile.

    Returns all user fields including preferences.
    """
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the current user's profile and preferences.

    Only fields provided in the request body are updated.
    All fields are optional (partial update).

    Updatable fields:
    - name: Display name
    - avatar_url: Profile photo URL
    - preferred_units: "metric" or "imperial"
    - default_servings: Default serving count for recipes
    - voice_enabled: Whether voice features are enabled by default
    """
    update_data = body.model_dump(exclude_unset=True)
    updated_user = user_service.update(db, current_user, update_data)
    return updated_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Permanently delete the current user's account.

    This is a destructive operation that:
    - Deletes the user record
    - Cascades to delete all recipes owned by the user
    - Cascades to delete all collections owned by the user
    - Cascades to delete all cook logs by the user
    - Removes all nested data (ingredients, steps, equipment, etc.)

    Cannot be undone.
    """
    user_service.delete(db, current_user)
    return None
