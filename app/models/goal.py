import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, Integer, String, DateTime, Date, Float, Enum, Text
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


class GoalType(str, enum.Enum):
    perpetual = "perpetual"    # ongoing metric-based goal with a target range
    achievement = "achievement"  # time-bounded goal with milestones
    habit = "habit"            # recurring behaviour tracked by weekly frequency


class HabitType(str, enum.Enum):
    count = "count"           # number of sessions/occurrences
    duration = "duration"     # total minutes
    consistency = "consistency"  # consecutive day streak
    volume = "volume"         # cumulative amount (steps, litres, etc.)


class HabitPeriod(str, enum.Enum):
    day = "day"
    week = "week"
    month = "month"


class Goal(Base):
    __tablename__ = "goals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    state = Column(Enum(GoalState), nullable=False, default=GoalState.draft)
    goal_type = Column(Enum(GoalType), nullable=True)
    target_date = Column(Date, nullable=True)
    weekly_time_hours = Column(Float, nullable=True)
    weekly_tss = Column(Float, nullable=True)
    weekly_target = Column(Integer, nullable=True)  # habit goals: target frequency per week

    # Perpetual goal drift detection — metric type and acceptable range
    target_metric_type = Column(String(50), nullable=True)
    target_min = Column(Float, nullable=True)
    target_max = Column(Float, nullable=True)
    # When True, drift detection is suppressed (user-acknowledged recovery period)
    is_recovering = Column(Boolean, nullable=False, default=False)

    # Template and habit metadata
    template_id = Column(String(100), nullable=True)
    habit_type = Column(Enum(HabitType), nullable=True)
    habit_unit = Column(String(50), nullable=True)
    habit_period = Column(Enum(HabitPeriod), nullable=True)
    capture_keywords = Column(Text, nullable=True)  # JSON array of keyword strings

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
