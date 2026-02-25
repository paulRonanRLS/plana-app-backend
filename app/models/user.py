import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"usr_{uuid.uuid4().hex[:12]}")
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    auth_provider: Mapped[str] = mapped_column(String(20))  # google | apple
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    preferred_units: Mapped[str] = mapped_column(String(20), default="metric")
    default_servings: Mapped[int] = mapped_column(default=4)
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    recipes = relationship("Recipe", back_populates="owner", cascade="all, delete-orphan")
    collections = relationship("Collection", back_populates="owner", cascade="all, delete-orphan")
    cook_logs = relationship("CookLog", back_populates="user", cascade="all, delete-orphan")
