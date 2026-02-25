import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"col_{uuid.uuid4().hex[:12]}")
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover: Mapped[str | None] = mapped_column(String(500), nullable=True)  # emoji, URL, or auto-mosaic
    type: Mapped[str] = mapped_column(String(20), default="manual")  # manual | smart
    smart_rule: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="collections")
    recipe_memberships = relationship("CollectionRecipe", back_populates="collection", cascade="all, delete-orphan", order_by="CollectionRecipe.sort_order")
    collaborators = relationship("Collaborator", back_populates="collection", cascade="all, delete-orphan")


class CollectionRecipe(Base):
    __tablename__ = "collection_recipes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"cr_{uuid.uuid4().hex[:12]}")
    collection_id: Mapped[str] = mapped_column(String, ForeignKey("collections.id"), index=True)
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    added_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))

    # Relationships
    collection = relationship("Collection", back_populates="recipe_memberships")
    recipe = relationship("Recipe", back_populates="collection_memberships")


class Collaborator(Base):
    __tablename__ = "collaborators"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"clb_{uuid.uuid4().hex[:12]}")
    collection_id: Mapped[str] = mapped_column(String, ForeignKey("collections.id"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), default="editor")  # editor | viewer
    invited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    collection = relationship("Collection", back_populates="collaborators")
