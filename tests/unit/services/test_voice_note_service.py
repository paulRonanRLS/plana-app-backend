"""
Unit tests for voice note service business logic.
"""

import pytest
import io
from datetime import datetime, timezone
from fastapi import HTTPException, UploadFile

from app.services import voice_note_service
from app.models.cook_log import CookLog, VoiceNote


def test_create_voice_note_saves_file_and_record(test_user, test_recipe, test_db):
    """Test creating a voice note saves file and creates record."""
    user = test_user["user"]

    # Create cook log
    cook_log = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=4,
        rating=5,
    )
    test_db.add(cook_log)
    test_db.commit()

    # Create fake audio file
    fake_audio = io.BytesIO(b"fake audio data")
    file = UploadFile(filename="note.mp3", file=fake_audio)

    # Create voice note
    voice_note = voice_note_service.create(test_db, cook_log, file, step_number=2)

    assert voice_note.id is not None
    assert voice_note.cook_log_id == cook_log.id
    assert voice_note.step_number == 2
    assert voice_note.audio_url is not None
    assert "voice-notes" in voice_note.audio_url
    assert cook_log.id in voice_note.audio_url


def test_create_voice_note_without_step_number(test_user, test_recipe, test_db):
    """Test creating a voice note without step number."""
    user = test_user["user"]

    # Create cook log
    cook_log = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=4,
        rating=5,
    )
    test_db.add(cook_log)
    test_db.commit()

    # Create fake audio file
    fake_audio = io.BytesIO(b"fake audio data")
    file = UploadFile(filename="note.mp3", file=fake_audio)

    # Create voice note without step number
    voice_note = voice_note_service.create(test_db, cook_log, file)

    assert voice_note.step_number is None


def test_delete_voice_note_removes_file_and_record(test_user, test_recipe, test_db):
    """Test deleting a voice note removes file and record."""
    user = test_user["user"]

    # Create cook log
    cook_log = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=4,
        rating=5,
    )
    test_db.add(cook_log)
    test_db.commit()

    # Create fake audio file
    fake_audio = io.BytesIO(b"fake audio data")
    file = UploadFile(filename="note.mp3", file=fake_audio)

    # Create voice note
    voice_note = voice_note_service.create(test_db, cook_log, file)
    voice_note_id = voice_note.id

    # Delete voice note
    voice_note_service.delete(test_db, voice_note, user)

    # Verify record is deleted
    deleted = test_db.query(VoiceNote).filter(VoiceNote.id == voice_note_id).first()
    assert deleted is None


def test_delete_voice_note_wrong_user_raises_403(test_user, test_other_user, test_db):
    """Test deleting voice note owned by another user raises 403."""
    owner = test_user["user"]
    other = test_other_user["user"]

    # Create recipe owned by owner
    from app.models.recipe import Recipe
    recipe = Recipe(owner_id=owner.id, title="Test", source_type="manual", base_servings=4)
    test_db.add(recipe)
    test_db.commit()

    # Create cook log owned by owner
    cook_log = CookLog(
        recipe_id=recipe.id,
        user_id=owner.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=4,
        rating=5,
    )
    test_db.add(cook_log)
    test_db.commit()

    # Create voice note
    fake_audio = io.BytesIO(b"fake audio data")
    file = UploadFile(filename="note.mp3", file=fake_audio)
    voice_note = voice_note_service.create(test_db, cook_log, file)

    # Other user tries to delete it
    with pytest.raises(HTTPException) as exc_info:
        voice_note_service.delete(test_db, voice_note, other)

    assert exc_info.value.status_code == 403
