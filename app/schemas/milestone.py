"""Pydantic schemas for milestone endpoints."""

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.milestone import MilestoneState


class MilestoneSuggestRequest(BaseModel):
    activity_type: Optional[str] = None  # "run" | "ride" | "general" — inferred if omitted


class SuggestedMilestone(BaseModel):
    title: str
    description: Optional[str] = None
    target_date: Optional[str] = None   # YYYY-MM-DD string from LLM output
    sequence: int = 1


class CapabilitySnapshot(BaseModel):
    goal_type: str
    long_run_km: Optional[float] = None
    weekly_volume_km: Optional[float] = None
    avg_pace_min_per_km: Optional[float] = None
    ftp_estimate_w: Optional[float] = None
    longest_ride_km: Optional[float] = None
    weekly_tss: Optional[float] = None


class MilestoneSuggestResponse(BaseModel):
    goal_id: int
    activity_type: str
    suggestions: list[SuggestedMilestone]
    capability: CapabilitySnapshot


class MilestoneAgreeItem(BaseModel):
    title: str
    description: Optional[str] = None
    target_date: Optional[date] = None
    sequence: Optional[int] = None


class MilestoneAgreeRequest(BaseModel):
    milestones: list[MilestoneAgreeItem]


class MilestoneResponse(BaseModel):
    id: int
    goal_id: int
    title: str
    description: Optional[str] = None
    state: MilestoneState
    sequence: int
    target_date: Optional[date] = None
    created_at: datetime
    updated_at: datetime
    achieved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MilestoneListResponse(BaseModel):
    goal_id: int
    milestones: list[MilestoneResponse]


class MilestonePatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    target_date: Optional[date] = None
    state: Optional[MilestoneState] = None
