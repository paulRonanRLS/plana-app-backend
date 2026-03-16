"""
Integration tests for collections router - key endpoints.
"""

import pytest


def test_create_collection(test_user):
    """Test POST /collections creates a manual collection."""
    client = test_user["client"]
    headers = test_user["headers"]

    collection_data = {
        "name": "My First Collection",
        "description": "A collection of my favorite recipes",
        "cover": "🍝",
        "recipe_ids": [],
    }

    response = client.post("/v1/collections", headers=headers, json=collection_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My First Collection"
    assert data["type"] == "manual"
    assert data["description"] == "A collection of my favorite recipes"
    assert data["cover"] == "🍝"
    assert "id" in data
    assert "owner" in data


def test_list_collections(test_user):
    """Test GET /collections returns owned collections."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create two collections
    client.post("/v1/collections", headers=headers, json={"name": "Collection 1", "recipe_ids": []})
    client.post("/v1/collections", headers=headers, json={"name": "Collection 2", "recipe_ids": []})

    # List collections
    response = client.get("/v1/collections", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert "collections" in data
    assert len(data["collections"]) == 2


def test_get_collection(test_user):
    """Test GET /collections/{id} returns full collection detail."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create collection
    create_response = client.post(
        "/v1/collections",
        headers=headers,
        json={"name": "Test Collection", "recipe_ids": []}
    )
    collection_id = create_response.json()["id"]

    # Get collection
    response = client.get(f"/v1/collections/{collection_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == collection_id
    assert data["name"] == "Test Collection"
    assert "recipes" in data
    assert "collaborators" in data
    assert "owner" in data


def test_update_collection(test_user):
    """Test PATCH /collections/{id} updates collection metadata."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create collection
    create_response = client.post(
        "/v1/collections",
        headers=headers,
        json={"name": "Original Name", "description": "Original description", "recipe_ids": []}
    )
    collection_id = create_response.json()["id"]

    # Update name only
    update_data = {"name": "Updated Name"}
    response = client.patch(f"/v1/collections/{collection_id}", headers=headers, json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "Original description"  # Unchanged


def test_delete_collection(test_user):
    """Test DELETE /collections/{id} deletes collection."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create collection
    create_response = client.post(
        "/v1/collections",
        headers=headers,
        json={"name": "To Delete", "recipe_ids": []}
    )
    collection_id = create_response.json()["id"]

    # Delete collection
    response = client.delete(f"/v1/collections/{collection_id}", headers=headers)

    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/v1/collections/{collection_id}", headers=headers)
    assert get_response.status_code == 404


def test_add_recipes_to_collection(test_user, test_recipe):
    """Test POST /collections/{id}/recipes adds recipes."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create collection
    create_response = client.post(
        "/v1/collections",
        headers=headers,
        json={"name": "Recipe Collection", "recipe_ids": []}
    )
    collection_id = create_response.json()["id"]

    # Add recipe
    add_data = {"recipe_ids": [test_recipe.id]}
    response = client.post(f"/v1/collections/{collection_id}/recipes", headers=headers, json=add_data)

    assert response.status_code == 201
    assert response.json()["status"] == "ok"

    # Verify recipe was added
    get_response = client.get(f"/v1/collections/{collection_id}", headers=headers)
    data = get_response.json()
    assert len(data["recipes"]) == 1
    assert data["recipes"][0]["id"] == test_recipe.id


def test_remove_recipe_from_collection(test_user, test_recipe):
    """Test DELETE /collections/{id}/recipes/{recipe_id} removes recipe."""
    client = test_user["client"]
    headers = test_user["headers"]

    # Create collection with recipe
    create_response = client.post(
        "/v1/collections",
        headers=headers,
        json={"name": "Test", "recipe_ids": [test_recipe.id]}
    )
    collection_id = create_response.json()["id"]

    # Remove recipe
    response = client.delete(
        f"/v1/collections/{collection_id}/recipes/{test_recipe.id}",
        headers=headers
    )

    assert response.status_code == 204

    # Verify recipe was removed
    get_response = client.get(f"/v1/collections/{collection_id}", headers=headers)
    data = get_response.json()
    assert len(data["recipes"]) == 0


def test_reorder_recipes(test_user, test_db):
    """Test PATCH /collections/{id}/reorder updates recipe order."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create 3 recipes
    from app.models.recipe import Recipe
    recipe1 = Recipe(owner_id=user.id, title="Recipe 1", source_type="manual", base_servings=4)
    recipe2 = Recipe(owner_id=user.id, title="Recipe 2", source_type="manual", base_servings=4)
    recipe3 = Recipe(owner_id=user.id, title="Recipe 3", source_type="manual", base_servings=4)
    test_db.add_all([recipe1, recipe2, recipe3])
    test_db.commit()

    # Create collection with recipes in order 1,2,3
    create_response = client.post(
        "/v1/collections",
        headers=headers,
        json={"name": "Test", "recipe_ids": [recipe1.id, recipe2.id, recipe3.id]}
    )
    collection_id = create_response.json()["id"]

    # Reorder to 3,1,2
    reorder_data = {"recipe_order": [recipe3.id, recipe1.id, recipe2.id]}
    response = client.patch(f"/v1/collections/{collection_id}/reorder", headers=headers, json=reorder_data)

    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Verify new order
    get_response = client.get(f"/v1/collections/{collection_id}", headers=headers)
    data = get_response.json()
    assert data["recipes"][0]["id"] == recipe3.id
    assert data["recipes"][1]["id"] == recipe1.id
    assert data["recipes"][2]["id"] == recipe2.id


def test_create_smart_collection(test_user):
    """Test POST /collections/smart creates smart collection."""
    client = test_user["client"]
    headers = test_user["headers"]

    smart_data = {
        "name": "Quick Italian Recipes",
        "smart_rule": {
            "filters": [
                {"field": "cuisine", "operator": "equals", "value": "Italian"},
                {"field": "total_time", "operator": "lte", "value": 30}
            ],
            "sort": "title",
            "limit": 50
        }
    }

    response = client.post("/v1/collections/smart", headers=headers, json=smart_data)

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Quick Italian Recipes"
    assert data["type"] == "smart"
    assert data["smart_rule"] is not None
    assert len(data["smart_rule"]["filters"]) == 2


def test_smart_collection_resolves_recipes(test_user, test_db):
    """Test that smart collection dynamically resolves matching recipes."""
    client = test_user["client"]
    headers = test_user["headers"]
    user = test_user["user"]

    # Create Italian and Mexican recipes
    from app.models.recipe import Recipe
    italian = Recipe(
        owner_id=user.id,
        title="Pasta",
        cuisine="Italian",
        source_type="manual",
        base_servings=4
    )
    mexican = Recipe(
        owner_id=user.id,
        title="Tacos",
        cuisine="Mexican",
        source_type="manual",
        base_servings=4
    )
    test_db.add_all([italian, mexican])
    test_db.commit()

    # Create smart collection for Italian recipes
    smart_data = {
        "name": "Italian Only",
        "smart_rule": {
            "filters": [{"field": "cuisine", "operator": "equals", "value": "Italian"}]
        }
    }
    response = client.post("/v1/collections/smart", headers=headers, json=smart_data)
    collection_id = response.json()["id"]

    # Get collection - should only contain Italian recipe
    get_response = client.get(f"/v1/collections/{collection_id}", headers=headers)
    data = get_response.json()

    assert len(data["recipes"]) == 1
    assert data["recipes"][0]["id"] == italian.id


def test_duplicate_collection(test_user, test_other_user, test_db):
    """Test POST /collections/{id}/duplicate duplicates collection and recipes."""
    owner_client = test_user["client"]
    owner_headers = test_user["headers"]
    owner = test_user["user"]

    other_client = test_other_user["client"]
    other_headers = test_other_user["headers"]
    other = test_other_user["user"]

    # Owner creates recipe and collection
    from app.models.recipe import Recipe
    recipe = Recipe(
        owner_id=owner.id,
        title="Owner's Recipe",
        source_type="manual",
        base_servings=4
    )
    test_db.add(recipe)
    test_db.commit()

    create_response = owner_client.post(
        "/v1/collections",
        headers=owner_headers,
        json={"name": "Original Collection", "recipe_ids": [recipe.id]}
    )
    collection_id = create_response.json()["id"]

    # Other user duplicates the collection
    # First, add other user as collaborator so they can access it
    from app.models.collection import Collaborator
    from datetime import datetime, timezone
    collab = Collaborator(
        collection_id=collection_id,
        user_id=other.id,
        role="viewer",
        accepted_at=datetime.now(timezone.utc)
    )
    test_db.add(collab)
    test_db.commit()

    # Now duplicate
    dup_response = other_client.post(
        f"/v1/collections/{collection_id}/duplicate",
        headers=other_headers
    )

    assert dup_response.status_code == 201
    dup_data = dup_response.json()
    assert "new_collection_id" in dup_data
    assert dup_data["recipes_duplicated"] == 1

    # Verify new collection exists and is owned by other user
    new_collection_id = dup_data["new_collection_id"]
    get_response = other_client.get(f"/v1/collections/{new_collection_id}", headers=other_headers)
    data = get_response.json()

    assert data["name"] == "Original Collection (Copy)"
    assert data["owner"]["id"] == other.id
    assert len(data["recipes"]) == 1


def test_collection_not_found(test_user):
    """Test accessing non-existent collection returns 404."""
    client = test_user["client"]
    headers = test_user["headers"]

    response = client.get("/v1/collections/nonexistent", headers=headers)

    assert response.status_code == 404


def test_collection_access_denied(test_user, test_other_user):
    """Test accessing other user's private collection returns 403."""
    owner_client = test_user["client"]
    owner_headers = test_user["headers"]

    other_client = test_other_user["client"]
    other_headers = test_other_user["headers"]

    # Owner creates private collection
    create_response = owner_client.post(
        "/v1/collections",
        headers=owner_headers,
        json={"name": "Private", "recipe_ids": []}
    )
    collection_id = create_response.json()["id"]

    # Other user tries to access it
    response = other_client.get(f"/v1/collections/{collection_id}", headers=other_headers)

    assert response.status_code == 403
