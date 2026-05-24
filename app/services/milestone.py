"""Milestone CRUD — thin service layer over the Milestone model."""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.milestone import Milestone, MilestoneState


def _now() -> datetime:
    return datetime.now(timezone.utc)


def list_milestones(db: Session, goal_id: int) -> list[Milestone]:
    return (
        db.query(Milestone)
        .filter(Milestone.goal_id == goal_id)
        .order_by(Milestone.sequence, Milestone.created_at)
        .all()
    )


def get_milestone(db: Session, goal_id: int, milestone_id: int) -> Milestone:
    m = (
        db.query(Milestone)
        .filter(Milestone.goal_id == goal_id, Milestone.id == milestone_id)
        .first()
    )
    if m is None:
        raise HTTPException(status_code=404, detail=f"Milestone {milestone_id} not found on goal {goal_id}")
    return m


def create_milestones(
    db: Session,
    goal_id: int,
    items: list[dict],
    state: MilestoneState = MilestoneState.pending,
) -> list[Milestone]:
    """Persist a list of milestone dicts against a goal.

    Each dict may include: title (required), description, target_date, sequence.
    Sequence defaults to insertion order if omitted.
    """
    now = _now()
    saved: list[Milestone] = []
    for i, item in enumerate(items):
        seq = item.get("sequence") if item.get("sequence") is not None else (i + 1)
        raw_date = item.get("target_date")
        if isinstance(raw_date, str):
            try:
                raw_date = date.fromisoformat(raw_date)
            except ValueError:
                raw_date = None
        m = Milestone(
            goal_id=goal_id,
            title=item["title"],
            description=item.get("description"),
            target_date=raw_date,
            sequence=seq,
            state=state,
            created_at=now,
            updated_at=now,
        )
        db.add(m)
        saved.append(m)
    db.commit()
    for m in saved:
        db.refresh(m)
    return saved


def transition_suggested(db: Session, goal_id: int) -> list[Milestone]:
    """Transition all suggested milestones on a goal to pending."""
    now = _now()
    milestones = (
        db.query(Milestone)
        .filter(Milestone.goal_id == goal_id, Milestone.state == MilestoneState.suggested)
        .all()
    )
    for m in milestones:
        m.state = MilestoneState.pending
        m.updated_at = now
    if milestones:
        db.commit()
        for m in milestones:
            db.refresh(m)
    return milestones


def delete_milestone(db: Session, goal_id: int, milestone_id: int) -> None:
    m = get_milestone(db, goal_id, milestone_id)
    db.delete(m)
    db.commit()


def update_milestone(db: Session, goal_id: int, milestone_id: int, data: dict) -> Milestone:
    """Partial update. Setting state=achieved auto-fills achieved_at."""
    m = get_milestone(db, goal_id, milestone_id)
    now = _now()

    new_state = data.get("state")
    if new_state == MilestoneState.achieved and m.state != MilestoneState.achieved:
        data.setdefault("achieved_at", now)
    elif new_state is not None and new_state != MilestoneState.achieved:
        data["achieved_at"] = None

    for field, value in data.items():
        setattr(m, field, value)
    m.updated_at = now
    db.commit()
    db.refresh(m)
    return m
