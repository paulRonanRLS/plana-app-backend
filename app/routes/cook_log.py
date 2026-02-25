from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.recipe import Recipe
from app.models.cook_log import CookLog, VoiceNote
from app.schemas.cook_log import (
    CookLogCreate, CookLogUpdate, CookLogResponse,
    RecipeCookLogResponse, RecipeCookSummary,
    TimelineCookLogEntry, TimelineCookLogResponse, RecipeBrief,
    VoiceNoteResponse, VoiceNoteListResponse,
)

router = APIRouter(tags=["cook-log"])


# --- Per-recipe cook log ---

@router.post("/recipes/{recipe_id}/cook-log", response_model=CookLogResponse, status_code=201)
def create_cook_log(
    recipe_id: str,
    body: CookLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a cook log entry after cooking."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == current_user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    log = CookLog(
        recipe_id=recipe_id,
        user_id=current_user.id,
        servings_made=body.servings_made,
        rating=body.rating,
        notes=body.notes,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return CookLogResponse(
        id=log.id,
        recipe_id=log.recipe_id,
        cooked_at=log.cooked_at,
        servings_made=log.servings_made,
        rating=log.rating,
        notes=log.notes,
        voice_note_count=0,
    )


@router.get("/recipes/{recipe_id}/cook-log", response_model=RecipeCookLogResponse)
def get_recipe_cook_log(
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get cook history for a specific recipe."""
    logs = (
        db.query(CookLog)
        .filter(CookLog.recipe_id == recipe_id, CookLog.user_id == current_user.id)
        .order_by(CookLog.cooked_at.desc())
        .all()
    )

    entries = []
    for log in logs:
        vn_count = db.query(VoiceNote).filter(VoiceNote.cook_log_id == log.id).count()
        entries.append(CookLogResponse(
            id=log.id,
            recipe_id=log.recipe_id,
            cooked_at=log.cooked_at,
            servings_made=log.servings_made,
            rating=log.rating,
            notes=log.notes,
            voice_note_count=vn_count,
        ))

    # Summary
    ratings = [log.rating for log in logs if log.rating]
    summary = RecipeCookSummary(
        times_cooked=len(logs),
        avg_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
        last_cooked_at=logs[0].cooked_at if logs else None,
    )

    return RecipeCookLogResponse(entries=entries, summary=summary)


# --- Global cook log timeline ---

@router.get("/cook-log", response_model=TimelineCookLogResponse)
def get_cook_log_timeline(
    limit: int = Query(default=20, le=50),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user's full cook history across all recipes (timeline)."""
    query = (
        db.query(CookLog)
        .filter(CookLog.user_id == current_user.id)
        .order_by(CookLog.cooked_at.desc())
    )

    if cursor:
        from datetime import datetime
        import base64
        try:
            cursor_dt = datetime.fromisoformat(base64.b64decode(cursor).decode())
            query = query.filter(CookLog.cooked_at < cursor_dt)
        except Exception:
            pass

    logs = query.limit(limit + 1).all()
    has_more = len(logs) > limit
    logs = logs[:limit]

    entries = []
    for log in logs:
        recipe = db.query(Recipe).filter(Recipe.id == log.recipe_id).first()
        if recipe:
            entries.append(TimelineCookLogEntry(
                id=log.id,
                recipe=RecipeBrief(
                    id=recipe.id,
                    title=recipe.title,
                    cover_image_url=recipe.cover_image_url,
                ),
                cooked_at=log.cooked_at,
                rating=log.rating,
                notes=log.notes,
            ))

    import base64
    next_cursor = None
    if has_more and logs:
        next_cursor = base64.b64encode(logs[-1].cooked_at.isoformat().encode()).decode()

    return TimelineCookLogResponse(entries=entries, next_cursor=next_cursor, has_more=has_more)


@router.patch("/cook-log/{log_id}", response_model=CookLogResponse)
def update_cook_log(
    log_id: str,
    body: CookLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a cook log entry."""
    log = db.query(CookLog).filter(CookLog.id == log_id, CookLog.user_id == current_user.id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Cook log not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(log, field, value)
    db.commit()
    db.refresh(log)

    vn_count = db.query(VoiceNote).filter(VoiceNote.cook_log_id == log.id).count()
    return CookLogResponse(
        id=log.id,
        recipe_id=log.recipe_id,
        cooked_at=log.cooked_at,
        servings_made=log.servings_made,
        rating=log.rating,
        notes=log.notes,
        voice_note_count=vn_count,
    )


# --- Voice Notes ---

@router.post("/cook-log/{log_id}/voice-notes", response_model=VoiceNoteResponse, status_code=201)
def upload_voice_note(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a voice note. TODO: Accept multipart file upload."""
    log = db.query(CookLog).filter(CookLog.id == log_id, CookLog.user_id == current_user.id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Cook log not found")

    # TODO: Handle file upload, store to local disk or S3
    raise HTTPException(status_code=501, detail="Voice note upload not yet implemented")


@router.get("/cook-log/{log_id}/voice-notes", response_model=VoiceNoteListResponse)
def list_voice_notes(
    log_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all voice notes for a cook log entry."""
    notes = db.query(VoiceNote).filter(VoiceNote.cook_log_id == log_id).all()
    return VoiceNoteListResponse(
        voice_notes=[VoiceNoteResponse.model_validate(n) for n in notes],
    )


@router.delete("/voice-notes/{note_id}", status_code=204)
def delete_voice_note(
    note_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a voice note."""
    note = db.query(VoiceNote).filter(VoiceNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="Voice note not found")
    # Verify ownership through cook log
    log = db.query(CookLog).filter(CookLog.id == note.cook_log_id, CookLog.user_id == current_user.id).first()
    if not log:
        raise HTTPException(status_code=403, detail="Access denied")
    # TODO: Delete audio file from storage
    db.delete(note)
    db.commit()
