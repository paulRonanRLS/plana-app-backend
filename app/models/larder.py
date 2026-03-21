import uuid
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LarderItem(Base):
    __tablename__ = "larder_items"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_larder_items_user_id_name"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"ldr_{uuid.uuid4().hex[:12]}")
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    owner = relationship("User", back_populates="larder_items")
