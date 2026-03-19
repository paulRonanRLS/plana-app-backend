import os
from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from alembic import context

from app.database import Base

# Import all models so they're registered with Base.metadata
from app.models import (  # noqa: F401
    User, Recipe, Ingredient, Step, Equipment, Nutrition, Pairing,
    Collection, CollectionRecipe, Collaborator,
    CookLog, VoiceNote,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Resolve the database URL.
# Railway injects POSTGRES_URL for managed Postgres — check that first.
# Falls back to DATABASE_URL, then alembic.ini default for local dev.
DATABASE_URL = (
    os.environ.get("POSTGRES_URL")
    or os.environ.get("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
