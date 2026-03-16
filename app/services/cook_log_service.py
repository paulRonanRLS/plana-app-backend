"""
Cook log service for business logic operations.

Handles cook log CRUD, statistics, and date filtering.
"""

from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.models.cook_log import CookLog
from app.models.recipe import Recipe
from app.models.user import User


def create(db: Session, user: User, recipe_id: str, data: dict) -> CookLog:
    """
    Create a new cook log entry.

    Args:
        db: Database session
        user: User creating the log
        recipe_id: Recipe ID to log
        data: Cook log data (cooked_at, servings_made, rating, notes)

    Returns:
        Created CookLog object

    Raises:
        HTTPException: 404 if recipe not found or doesn't belong to user
    """
    # Verify recipe exists and belongs to user
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.owner_id == user.id
    ).first()

    if not recipe:
        raise HTTPException(
            status_code=404,
            detail="Recipe not found or you don't have access to it"
        )

    # Create cook log
    cook_log = CookLog(
        recipe_id=recipe_id,
        user_id=user.id,
        **data
    )

    db.add(cook_log)
    db.commit()
    db.refresh(cook_log)

    return cook_log


def list_for_recipe(db: Session, user: User, recipe_id: str) -> list[CookLog]:
    """
    List all cook logs for a specific recipe.

    Args:
        db: Database session
        user: User making the request
        recipe_id: Recipe ID to get logs for

    Returns:
        List of CookLog objects, ordered newest first

    Raises:
        HTTPException: 404 if recipe not found or doesn't belong to user
    """
    # Verify recipe exists and belongs to user
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.owner_id == user.id
    ).first()

    if not recipe:
        raise HTTPException(
            status_code=404,
            detail="Recipe not found or you don't have access to it"
        )

    # Get cook logs ordered newest first
    cook_logs = (
        db.query(CookLog)
        .options(joinedload(CookLog.voice_notes))
        .filter(CookLog.recipe_id == recipe_id)
        .order_by(CookLog.cooked_at.desc())
        .all()
    )

    return cook_logs


def list_for_user(
    db: Session,
    user: User,
    cooked_after: datetime | None = None,
    cooked_before: datetime | None = None
) -> list[CookLog]:
    """
    List all cook logs across all recipes for a user.

    Args:
        db: Database session
        user: User making the request
        cooked_after: Optional start date filter
        cooked_before: Optional end date filter

    Returns:
        List of CookLog objects, ordered newest first
    """
    query = (
        db.query(CookLog)
        .options(joinedload(CookLog.voice_notes))
        .filter(CookLog.user_id == user.id)
    )

    # Apply date filters if provided
    if cooked_after:
        query = query.filter(CookLog.cooked_at >= cooked_after)

    if cooked_before:
        query = query.filter(CookLog.cooked_at <= cooked_before)

    # Order newest first
    cook_logs = query.order_by(CookLog.cooked_at.desc()).all()

    return cook_logs


def get_stats_for_recipe(db: Session, user: User, recipe_id: str) -> dict:
    """
    Get cooking statistics for a recipe using SQL aggregates.

    Args:
        db: Database session
        user: User making the request
        recipe_id: Recipe ID to get stats for

    Returns:
        Dictionary with times_cooked, average_rating, last_cooked

    Raises:
        HTTPException: 404 if recipe not found or doesn't belong to user
    """
    # Verify recipe exists and belongs to user
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.owner_id == user.id
    ).first()

    if not recipe:
        raise HTTPException(
            status_code=404,
            detail="Recipe not found or you don't have access to it"
        )

    # Use SQL aggregates to compute stats
    stats = (
        db.query(
            func.count(CookLog.id).label("times_cooked"),
            func.avg(CookLog.rating).label("average_rating"),
            func.max(CookLog.cooked_at).label("last_cooked")
        )
        .filter(CookLog.recipe_id == recipe_id)
        .first()
    )

    # Return stats (with defaults if no logs exist)
    return {
        "times_cooked": stats.times_cooked or 0,
        "average_rating": float(stats.average_rating) if stats.average_rating else None,
        "last_cooked": stats.last_cooked
    }
