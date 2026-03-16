"""
Integration tests for cook logs router - key endpoints.
"""

import pytest
import io
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


def test_create_cook_log(test_user, test_recipe):
    """Test POST /recipes/{id}/cook-logs creates a cook log."""
    client = test_user["client"]
    headers = test_user["headers"]

    cook_log_data = {
        "cooked_at": datetime.now(timezone.utc).isoformat(),
        "servings_made": 4,
        "rating": 5,
        "notes": "Turned out great!",
    }

    response = client.post(
        f"/v1/recipes/{test_recipe.id}/cook-logs",
        headers=headers,
        json=cook_log_data
    )

    assert response.status_code == 201
    data = response.json()
    assert data["recipe_id"] == test_recipe.id
    assert data["servings_made"] == 4
    assert data["rating"] == 5
    assert data["notes"] == "Turned out great!"
    assert "voice_notes" in data
    assert isinstance(data["voice_notes"], list)


def test_list_cook_logs_for_recipe(test_user, test_recipe, test_db):
    """Test GET /recipes/{id}/cook-logs returns cook logs."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create 2 cook logs
    from app.models.cook_log import CookLog
    log1 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=datetime.now(timezone.utc) - timedelta(days=1),
        servings_made=4,
        rating=4,
    )
    log2 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=6,
        rating=5,
    )
    test_db.add_all([log1, log2])
    test_db.commit()

    # List logs
    response = client.get(f"/v1/recipes/{test_recipe.id}/cook-logs", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    # Should be ordered newest first
    assert data[0]["servings_made"] == 6
    assert data[1]["servings_made"] == 4


def test_get_recipe_stats(test_user, test_recipe, test_db):
    """Test GET /recipes/{id}/stats returns statistics."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create cook logs
    from app.models.cook_log import CookLog
    now = datetime.now(timezone.utc)
    log1 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=5),
        servings_made=4,
        rating=5,
    )
    log2 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=2),
        servings_made=4,
        rating=3,
    )
    log3 = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=now,
        servings_made=4,
        rating=4,
    )
    test_db.add_all([log1, log2, log3])
    test_db.commit()

    # Get stats
    response = client.get(f"/v1/recipes/{test_recipe.id}/stats", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["times_cooked"] == 3
    assert data["average_rating"] == 4.0  # (5 + 3 + 4) / 3
    assert data["last_cooked"] is not None


def test_get_recipe_stats_no_logs(test_user, test_recipe):
    """Test GET /recipes/{id}/stats returns zeros when no logs exist."""
    client = test_user["client"]
    headers = test_user["headers"]

    response = client.get(f"/v1/recipes/{test_recipe.id}/stats", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["times_cooked"] == 0
    assert data["average_rating"] is None
    assert data["last_cooked"] is None


def test_list_cook_logs_date_filter(test_user, test_db):
    """Test GET /cook-logs with date filters."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create recipe
    from app.models.recipe import Recipe
    recipe = Recipe(owner_id=user.id, title="Test", source_type="manual", base_servings=4)
    test_db.add(recipe)
    test_db.commit()

    # Create cook logs across different dates
    from app.models.cook_log import CookLog
    now = datetime.now(timezone.utc)
    old_log = CookLog(
        recipe_id=recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=10),
        servings_made=4,
        rating=4,
    )
    recent_log = CookLog(
        recipe_id=recipe.id,
        user_id=user.id,
        cooked_at=now - timedelta(days=2),
        servings_made=4,
        rating=5,
    )
    test_db.add_all([old_log, recent_log])
    test_db.commit()

    # Filter: last 7 days
    cutoff = (now - timedelta(days=7)).isoformat()
    response = client.get(f"/v1/cook-logs?cooked_after={quote(cutoff)}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["rating"] == 5  # Should only get recent_log


def test_upload_voice_note(test_user, test_recipe, test_db):
    """Test POST /cook-logs/{id}/voice-notes uploads voice note."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create cook log
    from app.models.cook_log import CookLog
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
    files = {"file": ("note.mp3", fake_audio, "audio/mpeg")}
    data = {"step_number": 2}

    response = client.post(
        f"/v1/cook-logs/{cook_log.id}/voice-notes",
        headers=headers,
        files=files,
        data=data
    )

    assert response.status_code == 201
    result = response.json()
    assert result["cook_log_id"] == cook_log.id
    assert result["step_number"] == 2
    assert result["audio_url"] is not None
    assert "voice-notes" in result["audio_url"]


def test_delete_voice_note(test_user, test_recipe, test_db):
    """Test DELETE /cook-logs/{log_id}/voice-notes/{note_id} deletes voice note."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create cook log
    from app.models.cook_log import CookLog, VoiceNote
    cook_log = CookLog(
        recipe_id=test_recipe.id,
        user_id=user.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=4,
        rating=5,
    )
    test_db.add(cook_log)
    test_db.commit()

    # Create voice note
    voice_note = VoiceNote(
        cook_log_id=cook_log.id,
        audio_url="http://localhost:8000/uploads/voice-notes/test/audio.mp3",
        duration_seconds=30,
    )
    test_db.add(voice_note)
    test_db.commit()

    # Delete voice note
    response = client.delete(
        f"/v1/cook-logs/{cook_log.id}/voice-notes/{voice_note.id}",
        headers=headers
    )

    assert response.status_code == 204

    # Verify it's deleted
    deleted = test_db.query(VoiceNote).filter(VoiceNote.id == voice_note.id).first()
    assert deleted is None


def test_create_cook_log_for_nonexistent_recipe(test_user):
    """Test creating cook log for non-existent recipe returns 404."""
    client = test_user["client"]
    headers = test_user["headers"]

    cook_log_data = {
        "cooked_at": datetime.now(timezone.utc).isoformat(),
        "servings_made": 4,
        "rating": 5,
    }

    response = client.post(
        "/v1/recipes/nonexistent/cook-logs",
        headers=headers,
        json=cook_log_data
    )

    assert response.status_code == 404


def test_upload_voice_note_wrong_user(test_user, test_other_user, test_db):
    """Test uploading voice note to another user's cook log returns 403."""
    owner = test_user["user"]
    other_client = test_other_user["client"]
    other_headers = test_other_user["headers"]

    # Create recipe owned by owner
    from app.models.recipe import Recipe
    recipe = Recipe(owner_id=owner.id, title="Test", source_type="manual", base_servings=4)
    test_db.add(recipe)
    test_db.commit()

    # Create cook log owned by owner
    from app.models.cook_log import CookLog
    cook_log = CookLog(
        recipe_id=recipe.id,
        user_id=owner.id,
        cooked_at=datetime.now(timezone.utc),
        servings_made=4,
        rating=5,
    )
    test_db.add(cook_log)
    test_db.commit()

    # Other user tries to upload voice note
    fake_audio = io.BytesIO(b"fake audio data")
    files = {"file": ("note.mp3", fake_audio, "audio/mpeg")}

    response = other_client.post(
        f"/v1/cook-logs/{cook_log.id}/voice-notes",
        headers=other_headers,
        files=files
    )

    assert response.status_code == 403
