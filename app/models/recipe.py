import uuid
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, Text, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"rcp_{uuid.uuid4().hex[:12]}")
    owner_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_type: Mapped[str] = mapped_column(String(20))  # photo | manual | instagram | url
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    source_attribution: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    difficulty: Mapped[str | None] = mapped_column(String(20), nullable=True)  # easy | medium | hard
    prep_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cook_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_time: Mapped[int | None] = mapped_column(Integer, nullable=True)
    base_servings: Mapped[int] = mapped_column(Integer, default=4)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("User", back_populates="recipes")
    ingredients = relationship("Ingredient", back_populates="recipe", cascade="all, delete-orphan", order_by="Ingredient.sort_order")
    steps = relationship("Step", back_populates="recipe", cascade="all, delete-orphan", order_by="Step.step_number")
    equipment = relationship("Equipment", back_populates="recipe", cascade="all, delete-orphan")
    nutrition = relationship("Nutrition", back_populates="recipe", uselist=False, cascade="all, delete-orphan")
    pairing = relationship("Pairing", back_populates="recipe", uselist=False, cascade="all, delete-orphan")
    cook_logs = relationship("CookLog", back_populates="recipe", cascade="all, delete-orphan")
    collection_memberships = relationship("CollectionRecipe", back_populates="recipe", cascade="all, delete-orphan")


class Ingredient(Base):
    __tablename__ = "ingredients"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"ing_{uuid.uuid4().hex[:12]}")
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    group_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_optional: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    recipe = relationship("Recipe", back_populates="ingredients")


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"stp_{uuid.uuid4().hex[:12]}")
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), index=True)
    step_number: Mapped[int] = mapped_column(Integer)
    instruction: Mapped[str] = mapped_column(Text)
    timer_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section_label: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    recipe = relationship("Recipe", back_populates="steps")


class Equipment(Base):
    __tablename__ = "equipment"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"eqp_{uuid.uuid4().hex[:12]}")
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_essential: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    recipe = relationship("Recipe", back_populates="equipment")


class Nutrition(Base):
    __tablename__ = "nutrition"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"nut_{uuid.uuid4().hex[:12]}")
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), unique=True)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    protein_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    carbs_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    fat_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    fiber_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    sugar_g: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | ai_estimated | fetched
    confidence: Mapped[str] = mapped_column(String(20), default="estimated")  # verified | estimated

    # Relationships
    recipe = relationship("Recipe", back_populates="nutrition")


class Pairing(Base):
    __tablename__ = "pairings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: f"par_{uuid.uuid4().hex[:12]}")
    recipe_id: Mapped[str] = mapped_column(String, ForeignKey("recipes.id"), unique=True)
    suggestion: Mapped[str] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    recipe = relationship("Recipe", back_populates="pairing")
