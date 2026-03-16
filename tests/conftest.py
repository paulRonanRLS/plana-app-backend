"""
Pytest fixtures for testing.

Provides:
- test_db: SQLite in-memory database session (fresh per test)
- test_app: FastAPI TestClient with dependency overrides
- test_user: Authenticated user with auth headers
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, JSON, String
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import ARRAY

from app.main import app
from app.database import Base
from app.dependencies.db import get_db
from app.models.user import User
from app.models.recipe import Recipe, Ingredient, Step


@pytest.fixture
def test_db():
    """
    Create an in-memory SQLite database for testing.

    Fresh database created for each test function.
    Tables are created from SQLAlchemy models and dropped after test completes.

    Note: PostgreSQL ARRAY types are converted to JSON for SQLite compatibility.
    """
    # Replace ARRAY columns with JSON for SQLite compatibility
    # Access the actual column from the table metadata
    recipes_table = Base.metadata.tables.get('recipes')
    original_type = None
    if recipes_table is not None:
        tags_column = recipes_table.columns.get('tags')
        if tags_column is not None:
            # Store original type
            original_type = tags_column.type
            # Replace with JSON for SQLite
            tags_column.type = JSON()

    # Create in-memory SQLite engine
    # Use StaticPool to ensure single connection is reused
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # Keep single connection alive
        echo=False,  # Set to True to see SQL queries
    )

    # Create all tables from Base metadata
    Base.metadata.create_all(bind=engine)

    # Create session bound to the engine
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        yield db
    finally:
        db.close()
        # Don't dispose engine yet - let other fixtures finish
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

        # Restore original type if we modified it
        if original_type is not None and recipes_table is not None and tags_column is not None:
            tags_column.type = original_type


@pytest.fixture
def test_app(test_db: Session):
    """
    FastAPI TestClient with overridden database dependency.

    All requests made with this client will use the test database.
    """
    def override_get_db():
        """Override get_db dependency to use test database."""
        # Don't close the session - let test_db fixture handle it
        yield test_db

    # Override the get_db dependency
    app.dependency_overrides[get_db] = override_get_db

    # Create test client
    client = TestClient(app)

    yield client

    # Clean up overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_app: TestClient, test_db: Session):
    """
    Create a test user and return user object with auth headers.

    The auth dependency stub accepts any Bearer token as a Firebase UID.
    We use a fixed test UID so the user can be looked up consistently.

    This fixture depends on test_app to ensure it uses the same database instance.

    Returns:
        dict with keys:
        - user: User object
        - headers: dict with Authorization header for authenticated requests
        - client: TestClient for making requests
    """
    # Create test user
    user = User(
        firebase_uid="test-uid-12345",
        name="Test User",
        email="test@example.com",
        auth_provider="google",
        avatar_url=None,
        preferred_units="metric",
        default_servings=4,
        voice_enabled=True,
    )

    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Auth headers with fixed test UID
    # The auth stub will auto-create user with this UID if doesn't exist,
    # but we've pre-created it so we get consistent user IDs
    headers = {
        "Authorization": "Bearer test-uid-12345"
    }

    return {
        "user": user,
        "headers": headers,
        "client": test_app,
    }


@pytest.fixture
def test_recipe(test_user, test_db: Session):
    """
    Create a test recipe owned by test_user.

    Returns:
        Recipe object
    """
    user = test_user["user"]

    recipe = Recipe(
        owner_id=user.id,
        title="Test Recipe",
        description="A test recipe for testing",
        source_type="manual",
        cuisine="Italian",
        tags=["quick", "easy"],
        difficulty="easy",
        prep_time=10,
        cook_time=20,
        total_time=30,
        base_servings=4,
    )

    recipe.ingredients.append(Ingredient(
        name="flour",
        quantity=2,
        unit="cups",
        sort_order=1,
    ))

    recipe.steps.append(Step(
        step_number=1,
        instruction="Mix ingredients",
    ))

    test_db.add(recipe)
    test_db.commit()
    test_db.refresh(recipe)

    return recipe


@pytest.fixture
def test_other_user(test_app: TestClient, test_db: Session):
    """
    Create a second test user for multi-user testing.

    Returns:
        dict with keys:
        - user: User object
        - headers: dict with Authorization header
        - client: TestClient
    """
    user = User(
        firebase_uid="other-uid-67890",
        name="Other User",
        email="other@example.com",
        auth_provider="google",
        avatar_url=None,
        preferred_units="imperial",
        default_servings=2,
        voice_enabled=False,
    )

    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    headers = {
        "Authorization": "Bearer other-uid-67890"
    }

    return {
        "user": user,
        "headers": headers,
        "client": test_app,
    }
