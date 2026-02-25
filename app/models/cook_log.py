import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CookLog(Base):
    __tablename__ = "cook_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"log_{uuid.uuid4().hex[:12]}")
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    cooked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    servings_made: Mapped[int] = mapped_column(Integer)
    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    recipe = relationship("Recipe", back_populates="cook_logs")
    user = relationship("User", back_populates="cook_logs")
    voice_notes = relationship("VoiceNote", back_populates="cook_log", cascade="all, delete-orphan")


class VoiceNote(Base):
    __tablename__ = "voice_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"vn_{uuid.uuid4().hex[:12]}")
    cook_log_id: Mapped[str] = mapped_column(String, ForeignKey("cook_logs.id"), index=True)
    step_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_url: Mapped[str] = mapped_column(String(500))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    cook_log = relationship("CookLog", back_populates="voice_notes")
