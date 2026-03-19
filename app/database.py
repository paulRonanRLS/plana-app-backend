"""
Database configuration.

Creates the SQLAlchemy engine, session factory, and declarative base.
All models import Base from here to register themselves for migrations.

Railway injects the database URL as POSTGRES_URL. We check that first,
then fall back to DATABASE_URL, then the local development default.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


DATABASE_URL = (
    os.environ.get("POSTGRES_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql://recipe_user:recipe_dev_password@localhost:5432/recipe_app"
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
