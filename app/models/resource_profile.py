from datetime import datetime, timezone

from sqlalchemy import Column, Integer, Float, Date, DateTime, UniqueConstraint

from app.database import Base


class ResourceProfile(Base):
    """Weekly snapshot of the user's resource envelope.

    One row per ISO week. Updated as Garmin/Strava data arrives and as goals
    change their time/TSS commitments.

    Defaults reflect the spec baseline: ~62 hrs free time, ~320 TSS/week recovery budget.
    """

    __tablename__ = "resource_profiles"
    __table_args__ = (UniqueConstraint("week_start", name="uq_resource_profiles_week_start"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    week_start = Column(Date, nullable=False)    # ISO week Monday

    # Time resource — hours available after sleep and work
    time_envelope_hours = Column(Float, nullable=False, default=62.0)
    sleep_hours_per_night = Column(Float, nullable=True)
    work_hours_per_week = Column(Float, nullable=True)

    # Recovery resource — TSS budget derived from 90-day baseline
    recovery_envelope_tss = Column(Float, nullable=False, default=320.0)

    # Attention resource — open decisions + active milestones + unresolved episodes
    attention_count = Column(Integer, nullable=True)

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
