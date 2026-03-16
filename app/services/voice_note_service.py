"""
Voice note service for audio file management.

Handles voice note creation, deletion, and storage.
"""

import uuid
from pathlib import Path
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.cook_log import CookLog, VoiceNote
from app.models.user import User
from app.core.storage import get_storage


def create(
    db: Session,
    cook_log: CookLog,
    file: UploadFile,
    step_number: int | None = None
) -> VoiceNote:
    """
    Create a new voice note for a cook log.

    Args:
        db: Database session
        cook_log: CookLog to attach voice note to
        file: Uploaded audio file
        step_number: Optional step number the note relates to

    Returns:
        Created VoiceNote object
    """
    # Get file extension
    filename = file.filename or "audio.mp3"
    ext = Path(filename).suffix or ".mp3"

    # Generate unique storage path: voice-notes/{cook_log_id}/{uuid}.{ext}
    unique_id = uuid.uuid4().hex[:12]
    storage_path = f"voice-notes/{cook_log.id}/{unique_id}{ext}"

    # Save file to storage
    storage = get_storage()
    audio_url = storage.save(file.file, storage_path)

    # Create voice note record
    # TODO: Extract duration from audio file metadata
    # For now, default to 0 (frontend will send duration in future update)
    voice_note = VoiceNote(
        cook_log_id=cook_log.id,
        step_number=step_number,
        audio_url=audio_url,
        duration_seconds=0,  # TODO: extract from audio metadata
    )

    db.add(voice_note)
    db.commit()
    db.refresh(voice_note)

    return voice_note


def delete(db: Session, voice_note: VoiceNote, user: User) -> None:
    """
    Delete a voice note and its audio file.

    Args:
        db: Database session
        voice_note: VoiceNote to delete
        user: User making the request

    Raises:
        HTTPException: 403 if user doesn't own the cook log
    """
    # Get cook log to verify ownership
    cook_log = db.query(CookLog).filter(CookLog.id == voice_note.cook_log_id).first()

    if not cook_log or cook_log.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to delete this voice note"
        )

    # Extract storage path from audio_url
    # URL format: http://localhost:8000/uploads/voice-notes/log123/abc.mp3
    # We need: voice-notes/log123/abc.mp3
    audio_url = voice_note.audio_url
    if "/uploads/" in audio_url:
        storage_path = audio_url.split("/uploads/", 1)[1]
    else:
        # If URL format is different, try to extract path
        storage_path = audio_url.split("/")[-3:]  # Get last 3 parts
        storage_path = "/".join(storage_path)

    # Delete file from storage
    try:
        storage = get_storage()
        storage.delete(storage_path)
    except Exception:
        # Continue even if file deletion fails (file might not exist)
        pass

    # Delete voice note record
    db.delete(voice_note)
    db.commit()
