"""
User service for business logic operations.
"""

from sqlalchemy.orm import Session
from app.models.user import User


def get_by_id(db: Session, user_id: str) -> User | None:
    """
    Retrieve a user by their ID.

    Args:
        db: Database session
        user_id: User ID to look up

    Returns:
        User object if found, None otherwise
    """
    return db.query(User).filter(User.id == user_id).first()


def update(db: Session, user: User, update_data: dict) -> User:
    """
    Update user fields with partial data.

    Only fields present in update_data are modified.
    Excludes unset fields automatically.

    Args:
        db: Database session
        user: User object to update
        update_data: Dictionary of fields to update

    Returns:
        Updated User object
    """
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


def delete(db: Session, user: User) -> None:
    """
    Delete a user and all associated data.

    Cascade deletes:
    - All recipes owned by the user
    - All collections owned by the user
    - All cook logs by the user
    - All nested child records (ingredients, steps, equipment, etc.)

    Args:
        db: Database session
        user: User object to delete
    """
    db.delete(user)
    db.commit()
