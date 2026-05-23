import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, Date, Float, Enum, Text
from sqlalchemy.orm import relationship

from app.database import Base


class GoalState(str, enum.Enum):
    draft = "draft"
    active = "active"
    primacy = "primacy"
    subordinate = "subordinate"
    drifting = "drifting"
    released = "released"
    completed = "completed"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    state = Column(Enum(GoalState), nullable=False, default=GoalState.draft)
    target_date = Column(Date, nullable=True)
    weekly_time_hours = Column(Float, nullable=True)
    weekly_tss = Column(Float, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    released_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    release_reason = Column(Text, nullable=True)
    memoir = Column(Text, nullable=True)

    milestones = relationship("Milestone", back_populates="goal", cascade="all, delete-orphan")
    sacrifices = relationship("Sacrifice", back_populates="goal", cascade="all, delete-orphan")
