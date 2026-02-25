from pydantic import BaseModel
from datetime import datetime


class CookLogCreate(BaseModel):
    servings_made: int
    rating: int  # 1-5
    notes: str | None = None


class CookLogUpdate(BaseModel):
    rating: int | None = None
    notes: str | None = None


class CookLogResponse(BaseModel):
    id: str
    recipe_id: str
    cooked_at: datetime
    servings_made: int
    rating: int
    notes: str | None
    voice_note_count: int = 0

    model_config = {"from_attributes": True}


class RecipeCookSummary(BaseModel):
    times_cooked: int
    avg_rating: float | None
    last_cooked_at: datetime | None


class RecipeCookLogResponse(BaseModel):
    entries: list[CookLogResponse]
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
