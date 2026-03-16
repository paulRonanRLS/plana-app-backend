from pydantic import BaseModel, Field
from datetime import datetime


class VoiceNoteRead(BaseModel):
    """Voice note attached to a cook log."""
    id: str
    cook_log_id: str
    step_number: int | None
    audio_url: str
    duration_seconds: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CookLogCreate(BaseModel):
    """Create a new cook log entry."""
    cooked_at: datetime
    servings_made: int
    rating: int = Field(..., ge=1, le=5)  # 1-5 validated
    notes: str | None = None


class CookLogRead(BaseModel):
    """Full cook log with voice notes."""
    id: str
    recipe_id: str
    user_id: str
    cooked_at: datetime
    servings_made: int
    rating: int
    notes: str | None
    voice_notes: list[VoiceNoteRead] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class CookLogUpdate(BaseModel):
    rating: int | None = None
    notes: str | None = None


class RecipeStats(BaseModel):
    """Statistics about how many times a recipe has been cooked."""
    times_cooked: int
    average_rating: float | None
    last_cooked: datetime | None


class RecipeCookSummary(BaseModel):
    times_cooked: int
    avg_rating: float | None
    last_cooked_at: datetime | None


class RecipeCookLogResponse(BaseModel):
    entries: list[CookLogRead]
    summary: RecipeCookSummary


class RecipeBrief(BaseModel):
    id: str
    title: str
    cover_image_url: str | None


class TimelineCookLogEntry(BaseModel):
    id: str
    recipe: RecipeBrief
    cooked_at: datetime
    rating: int
    notes: str | None


class TimelineCookLogResponse(BaseModel):
    entries: list[TimelineCookLogEntry]
    next_cursor: str | None
    has_more: bool


class VoiceNoteResponse(BaseModel):
    id: str
    cook_log_id: str
    step_number: int | None
    audio_url: str
    duration_seconds: int
    created_at: datetime

    model_config = {"from_attributes": True}


class VoiceNoteListResponse(BaseModel):
    voice_notes: list[VoiceNoteResponse]
