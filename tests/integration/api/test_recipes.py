"""
Integration tests for recipe router - key endpoints.
"""

import pytest


def test_create_recipe(test_user):
    """Test POST /recipes creates a recipe."""
    client = test_user["client"]
    headers = test_user["headers"]

    recipe_data = {
        "title": "Pasta Carbonara",
        "description": "Classic Italian pasta",
        "source_type": "manual",
        "cuisine": "Italian",
        "base_servings": 4,
        "prep_time": 10,
        "cook_time": 15,
        "total_time": 25,
        "ingredients": [
            {"name": "spaghetti", "quantity": 400, "unit": "g", "sort_order": 1},
            {"name": "eggs", "quantity": 4, "unit": None, "sort_order": 2},
        ],
        "steps": [
            {"step_number": 1, "instruction": "Boil water"},
            {"step_number": 2, "instruction": "Cook pasta"},
        ],
        "equipment": [{"name": "pot", "is_essential": True}],
    }

    response = client.post("/v1/recipes", headers=headers, json=recipe_data)

    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Pasta Carbonara"
    assert data["cuisine"] == "Italian"
    assert len(data["ingredients"]) == 2
    assert len(data["steps"]) == 2
    assert data["ingredients"][0]["name"] == "spaghetti"


def test_list_recipes(test_user):
    """Test GET /recipes returns paginated list."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create a recipe first
    recipe_data = {
        "title": "Test Recipe",
        "source_type": "manual",
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }
    client.post("/v1/recipes", headers=headers, json=recipe_data)

    # List recipes
    response = client.get("/v1/recipes", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "recipes" in data
    assert "total_count" in data
    assert data["total_count"] >= 1


def test_get_recipe(test_user):
    """Test GET /recipes/{id} returns full recipe detail."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create a recipe
    recipe_data = {
        "title": "Get Test",
        "source_type": "manual",
        "base_servings": 2,
        "ingredients": [{"name": "flour", "quantity": 1, "unit": "cup", "sort_order": 1}],
        "steps": [{"step_number": 1, "instruction": "Mix"}],
        "equipment": [],
    }
    create_response = client.post("/v1/recipes", headers=headers, json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Get the recipe
    response = client.get(f"/v1/recipes/{recipe_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == recipe_id
    assert data["title"] == "Get Test"
    assert len(data["ingredients"]) == 1


def test_update_recipe(test_user):
    """Test PATCH /recipes/{id} updates recipe."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create a recipe
    recipe_data = {
        "title": "Original",
        "description": "Original description",
        "source_type": "manual",
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }
    create_response = client.post("/v1/recipes", headers=headers, json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Update title only
    update_data = {"title": "Updated Title"}
    response = client.patch(f"/v1/recipes/{recipe_id}", headers=headers, json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["description"] == "Original description"  # Unchanged


def test_delete_recipe(test_user):
    """Test DELETE /recipes/{id} deletes recipe."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create a recipe
    recipe_data = {
        "title": "To Delete",
        "source_type": "manual",
        "base_servings": 4,
        "ingredients": [],
        "steps": [],
        "equipment": [],
    }
    create_response = client.post("/v1/recipes", headers=headers, json=recipe_data)
    recipe_id = create_response.json()["id"]

    # Delete recipe
    response = client.delete(f"/v1/recipes/{recipe_id}", headers=headers)

    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/v1/recipes/{recipe_id}", headers=headers)
    assert get_response.status_code == 404


def test_recipe_not_found(test_user):
    """Test accessing non-existent recipe returns 404."""
    client = test_user["client"]
    headers = test_user["headers"]

    response = client.get("/v1/recipes/nonexistent_id", headers=headers)

    assert response.status_code == 404
