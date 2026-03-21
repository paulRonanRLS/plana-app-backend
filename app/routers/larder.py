from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.larder import LarderItem
from app.schemas.larder import LarderAddRequest, LarderListResponse, LarderItemResponse

router = APIRouter(prefix="/larder", tags=["larder"])


def _get_larder_response(db: Session, user_id: str) -> LarderListResponse:
    items = (
        db.query(LarderItem)
        .filter(LarderItem.user_id == user_id)
        .order_by(LarderItem.name.asc())
        .all()
    )
    return LarderListResponse(
        items=[LarderItemResponse.model_validate(i) for i in items],
        total=len(items),
    )


@router.get("", response_model=LarderListResponse)
def list_larder(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all larder items for the current user, ordered by name."""
    return _get_larder_response(db, current_user.id)


@router.post("", response_model=LarderListResponse)
def add_larder_items(
    body: LarderAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch add larder items. Duplicates are silently ignored."""
    for name in body.names:
        # Check if already exists — skip if so
        existing = (
            db.query(LarderItem)
            .filter(LarderItem.user_id == current_user.id, LarderItem.name == name)
            .first()
        )
        if not existing:
            db.add(LarderItem(user_id=current_user.id, name=name))
    db.commit()
    return _get_larder_response(db, current_user.id)


@router.delete("/{item_id}", status_code=204)
def delete_larder_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single larder item. Returns 404 if not found or wrong user."""
    item = (
        db.query(LarderItem)
        .filter(LarderItem.id == item_id, LarderItem.user_id == current_user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Larder item not found")
    db.delete(item)
    db.commit()


@router.delete("", status_code=204)
def clear_larder(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete all larder items for the current user."""
    db.query(LarderItem).filter(LarderItem.user_id == current_user.id).delete()
    db.commit()
