"""Milestone router — suggest, agree, list, and update milestones for a goal."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.claude_client import get_client
from app.dependencies.db import get_db
from app.intelligence.milestones import generate_milestones
from app.schemas.milestone import (
    CapabilitySnapshot,
    MilestoneAgreeRequest,
    MilestoneListResponse,
    MilestonePatch,
    MilestoneResponse,
    MilestoneSuggestRequest,
    MilestoneSuggestResponse,
    SuggestedMilestone,
)
from app.services.capability import get_capability_baseline, infer_goal_activity_type
from app.services.goal import get_goal
from app.services.milestone import create_milestones, list_milestones, update_milestone

router = APIRouter(prefix="/v1", tags=["milestones"])
logger = logging.getLogger(__name__)


@router.post("/goals/{goal_id}/milestones/suggest", response_model=MilestoneSuggestResponse)
def suggest_milestones(
    goal_id: int,
    body: MilestoneSuggestRequest,
    db: Session = Depends(get_db),
):
    """Generate a suggested milestone progression without saving anything.

    Uses the capability baseline derived from the last 90 days of Strava data.
    Returns 3 generic milestones in stub mode (CLAUDE_ENABLED=false).
    """
    goal = get_goal(db, goal_id)
    activity_type = body.activity_type or infer_goal_activity_type(goal)
    baseline = get_capability_baseline(db, activity_type)
    client = get_client()
    raw = generate_milestones(goal, baseline, client)

    suggestions = [
        SuggestedMilestone(
            title=m.get("title", ""),
            description=m.get("description"),
            target_date=m.get("target_date"),
            sequence=m.get("sequence", i + 1),
        )
        for i, m in enumerate(raw)
    ]

    capability = CapabilitySnapshot(
        goal_type=baseline.goal_type,
        long_run_km=baseline.long_run_km,
        weekly_volume_km=baseline.weekly_volume_km,
        avg_pace_min_per_km=baseline.avg_pace_min_per_km,
        ftp_estimate_w=baseline.ftp_estimate_w,
        longest_ride_km=baseline.longest_ride_km,
        weekly_tss=baseline.weekly_tss,
    )

    logger.info(f"suggest_milestones: goal={goal_id} type={activity_type} count={len(suggestions)}")
    return MilestoneSuggestResponse(
        goal_id=goal_id,
        activity_type=activity_type,
        suggestions=suggestions,
        capability=capability,
    )


@router.post("/goals/{goal_id}/milestones/agree", response_model=MilestoneListResponse)
def agree_milestones(
    goal_id: int,
    body: MilestoneAgreeRequest,
    db: Session = Depends(get_db),
):
    """Save agreed milestones against the goal.

    Accepts the list from /suggest (or a manually crafted list). Each milestone
    is saved as a Pending Milestone. Existing milestones are not affected.
    """
    if not body.milestones:
        raise HTTPException(status_code=422, detail="milestones list must not be empty")

    goal = get_goal(db, goal_id)
    items = [
        {
            "title": m.title,
            "description": m.description,
            "target_date": m.target_date,
            "sequence": m.sequence if m.sequence is not None else (i + 1),
        }
        for i, m in enumerate(body.milestones)
    ]
    saved = create_milestones(db, goal_id, items)
    logger.info(f"agree_milestones: goal={goal_id} saved={len(saved)}")
    return MilestoneListResponse(
        goal_id=goal_id,
        milestones=[MilestoneResponse.model_validate(m) for m in saved],
    )


@router.get("/goals/{goal_id}/milestones", response_model=MilestoneListResponse)
def get_milestones(goal_id: int, db: Session = Depends(get_db)):
    """List all milestones for a goal in sequence order."""
    get_goal(db, goal_id)  # 404 if goal not found
    milestones = list_milestones(db, goal_id)
    return MilestoneListResponse(
        goal_id=goal_id,
        milestones=[MilestoneResponse.model_validate(m) for m in milestones],
    )


@router.patch("/goals/{goal_id}/milestones/{milestone_id}", response_model=MilestoneResponse)
def patch_milestone(
    goal_id: int,
    milestone_id: int,
    body: MilestonePatch,
    db: Session = Depends(get_db),
):
    """Partial update — adjust date, mark complete, or edit description."""
    get_goal(db, goal_id)  # 404 if goal not found
    data = body.model_dump(exclude_unset=True)
    updated = update_milestone(db, goal_id, milestone_id, data)
    return MilestoneResponse.model_validate(updated)
