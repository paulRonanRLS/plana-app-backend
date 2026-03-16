"""
Unit tests for recipe service - focused on key business logic.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.recipe import Recipe
from app.services import recipe_service


def test_create_recipe_with_nested_data(test_db: Session, test_user):
    """Test creating a recipe with ingredients, steps, and equipment."""
    user = test_user["user"]

    recipe_data = {
        "title": "Test Recipe",
        "description": "A test recipe",
        "source_type": "manual",
        "base_servings": 4,
        "ingredients": [
            {"name": "flour", "quantity": 2, "unit": "cups", "sort_order": 1},
            {"name": "sugar", "quantity": 1, "unit": "cup", "sort_order": 2},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Mix ingredients"},
            {"step_number": 2, "instruction": "Bake at 350F"},
        ],
        "equipment": [{"name": "mixing bowl", "is_essential": True}],
    }

    recipe = recipe_service.create(test_db, user.id, recipe_data)

    assert recipe.title == "Test Recipe"
    assert recipe.owner_id == user.id
    assert len(recipe.ingredients) == 2
    assert len(recipe.steps) == 2
    assert len(recipe.equipment) == 1
    assert recipe.ingredients[0].name == "flour"
    assert recipe.steps[0].instruction == "Mix ingredients"


def test_get_by_id_with_ownership_check(test_db: Session, test_user):
    """Test retrieving recipe with ownership verification."""
    user = test_user["user"]

    recipe_data = {
        "title": "My Recipe",
        "source_type": "manual",
        "base_servings": 2,
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }

    created = recipe_service.create(test_db, user.id, recipe_data)

    # Can retrieve own recipe
    found = recipe_service.get_by_id(test_db, created.id, user.id)
    assert found is not None
    assert found.id == created.id

    # Cannot retrieve with wrong owner_id
    not_found = recipe_service.get_by_id(test_db, created.id, "wrong_owner")
    assert not_found is None


def test_update_recipe_partial(test_db: Session, test_user):
    """Test updating only specific fields of a recipe."""
    user = test_user["user"]

    recipe_data = {
        "title": "Original Title",
        "description": "Original description",
        "source_type": "manual",
        "base_servings": 4,
        "cuisine": "Italian",
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }

    recipe = recipe_service.create(test_db, user.id, recipe_data)

    # Update only title
    update_data = {"title": "Updated Title"}
    updated = recipe_service.update(test_db, recipe.id, user.id, update_data)

    assert updated is not None
    assert updated.title == "Updated Title"
    assert updated.description == "Original description"  # Unchanged
    assert updated.cuisine == "Italian"  # Unchanged


def test_update_recipe_replaces_nested_arrays(test_db: Session, test_user):
    """Test that updating ingredients/steps replaces the entire array."""
    user = test_user["user"]

    recipe_data = {
        "title": "Recipe",
        "source_type": "manual",
        "base_servings": 4,
        "ingredients": [
            {"name": "old ingredient", "quantity": 1, "unit": "cup", "sort_order": 1}
        ],
        "steps": [{"step_number": 1, "instruction": "Old step"}],
        "equipment": [],
    }

    recipe = recipe_service.create(test_db, user.id, recipe_data)
    assert len(recipe.ingredients) == 1

    # Update ingredients - should replace all
    update_data = {
        "ingredients": [
            {"name": "new ingredient 1", "quantity": 2, "unit": "cups", "sort_order": 1},
            {"name": "new ingredient 2", "quantity": 1, "unit": "tsp", "sort_order": 2},
        ]
    }

    updated = recipe_service.update(test_db, recipe.id, user.id, update_data)

    assert len(updated.ingredients) == 2
    assert updated.ingredients[0].name == "new ingredient 1"
    assert updated.ingredients[1].name == "new ingredient 2"


def test_delete_recipe(test_db: Session, test_user):
    """Test deleting a recipe."""
    user = test_user["user"]

    recipe_data = {
        "title": "To Delete",
        "source_type": "manual",
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }

    recipe = recipe_service.create(test_db, user.id, recipe_data)
    recipe_id = recipe.id

    # Delete recipe
    success = recipe_service.delete(test_db, recipe_id, user.id)
    assert success is True

    # Verify recipe no longer exists
    not_found = recipe_service.get_by_id(test_db, recipe_id, user.id)
    assert not_found is None


def test_add_note_appends_to_existing(test_db: Session, test_user):
    """Test adding a note appends to existing notes."""
    user = test_user["user"]

    recipe_data = {
        "title": "Recipe",
        "source_type": "manual",
        "base_servings": 4,
        "notes": "First note",
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }

    recipe = recipe_service.create(test_db, user.id, recipe_data)

    # Add second note
    updated = recipe_service.add_note(test_db, recipe.id, user.id, "Second note")

    assert updated is not None
    assert "First note" in updated.notes
    assert "Second note" in updated.notes
    assert updated.notes.count("\n") == 1  # One newline separator
