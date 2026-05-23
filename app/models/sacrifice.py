import enum
from datetime import datetime, timezone

from sqlalchemy import Column, Integer, DateTime, Date, Enum, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class ResourceType(str, enum.Enum):
    time = "time"
    recovery = "recovery"
    attention = "attention"
    willpower = "willpower"


class Sacrifice(Base):
    """Records each instance where a goal was missed or deprioritised.

    The resource field captures which of the four universal resources ran out.
    This attribution drives the longitudinal commitment profile.
    """

    __tablename__ = "sacrifices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal_id = Column(Integer, ForeignKey("goals.id"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    resource = Column(Enum(ResourceType), nullable=False)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    goal = relationship("Goal", back_populates="sacrifices")
