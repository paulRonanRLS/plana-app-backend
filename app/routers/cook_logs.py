"""
Cook log endpoints - manage cooking history and voice notes.

This router is a thin orchestration layer that delegates business logic to the service layer.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.cook_log import CookLog, VoiceNote
from app.schemas.cook_log import (
    CookLogCreate, CookLogUpdate, CookLogRead, RecipeStats, VoiceNoteRead
)
from app.services import cook_log_service, voice_note_service


router = APIRouter(tags=["cook-logs"])


@router.get("/recipes/{recipe_id}/cook-logs", response_model=list[CookLogRead])
def list_cook_logs_for_recipe(
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all cook logs for a specific recipe."""
    cook_logs = cook_log_service.list_for_recipe(db, current_user, recipe_id)
    return cook_logs


@router.post("/recipes/{recipe_id}/cook-logs", response_model=CookLogRead, status_code=201)
def create_cook_log(
    recipe_id: str,
    body: CookLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new cook log entry."""
    data = body.model_dump()
    cook_log = cook_log_service.create(db, current_user, recipe_id, data)
    return cook_log


@router.get("/recipes/{recipe_id}/stats", response_model=RecipeStats)
def get_recipe_stats(
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get cooking statistics for a recipe."""
    stats = cook_log_service.get_stats_for_recipe(db, current_user, recipe_id)
    return stats


@router.get("/cook-logs", response_model=list[CookLogRead])
def list_cook_logs_for_user(
    cooked_after: datetime | None = None,
    cooked_before: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all cook logs across all recipes for the current user.

    Query params:
    - cooked_after: ISO datetime string
    - cooked_before: ISO datetime string
    """
    cook_logs = cook_log_service.list_for_user(
        db, current_user, cooked_after, cooked_before
    )
    return cook_logs


@router.patch("/cook-logs/{cook_log_id}", response_model=CookLogRead)
def update_cook_log(
    cook_log_id: str,
    body: CookLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update rating and/or notes on a cook log entry."""
    data = body.model_dump(exclude_unset=True)
    return cook_log_service.update(db, current_user, cook_log_id, data)


@router.post("/cook-logs/{cook_log_id}/voice-notes", response_model=VoiceNoteRead, status_code=201)
def create_voice_note(
    cook_log_id: str,
    file: UploadFile = File(...),
    step_number: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a voice note for a cook log.

    Multipart/form-data:
    - file: Audio file
    - step_number: Optional step number (integer)
    """
    # Get cook log and verify ownership
    cook_log = db.query(CookLog).filter(CookLog.id == cook_log_id).first()

    if not cook_log:
        raise HTTPException(status_code=404, detail="Cook log not found")

    if cook_log.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to add voice notes to this cook log"
        )

    # Create voice note
    voice_note = voice_note_service.create(db, cook_log, file, step_number)
    return voice_note


@router.delete("/cook-logs/{cook_log_id}/voice-notes/{note_id}", status_code=204)
def delete_voice_note(
    cook_log_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a voice note."""
    # Get voice note
    voice_note = db.query(VoiceNote).filter(
        VoiceNote.id == note_id,
        VoiceNote.cook_log_id == cook_log_id
    ).first()

    if not voice_note:
        raise HTTPException(status_code=404, detail="Voice note not found")

    # Delete voice note (service handles ownership check)
    voice_note_service.delete(db, voice_note, current_user)
