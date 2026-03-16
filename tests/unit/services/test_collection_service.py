"""
Unit tests for collection service business logic.
"""

import pytest
from fastapi import HTTPException

from app.services import collection_service
from app.models.collection import Collection, CollectionRecipe, Collaborator
from app.models.recipe import Recipe, Ingredient, Step


def test_create_manual_collection(test_user, test_recipe, test_db):
    """Test creating a manual collection with initial recipes."""
    user = test_user["user"]

    data = {
        "name": "My Collection",
        "description": "Test collection",
        "type": "manual",
        "recipe_ids": [test_recipe.id],
    }

    collection = collection_service.create(test_db, user, data)

    assert collection.id is not None
    assert collection.name == "My Collection"
    assert collection.owner_id == user.id
    assert collection.type == "manual"

    # Check recipe was added
    memberships = test_db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id
    ).all()
    assert len(memberships) == 1
    assert memberships[0].recipe_id == test_recipe.id


def test_create_smart_collection(test_user, test_db):
    """Test creating a smart collection with filter rules."""
    user = test_user["user"]

    data = {
        "name": "Quick Italian Recipes",
        "type": "smart",
        "smart_rule": {
            "filters": [
                {"field": "cuisine", "operator": "equals", "value": "Italian"},
                {"field": "total_time", "operator": "lte", "value": 30}
            ],
            "sort": "title",
            "limit": 50
        }
    }

    collection = collection_service.create(test_db, user, data)

    assert collection.id is not None
    assert collection.type == "smart"
    assert collection.smart_rule is not None
    assert len(collection.smart_rule["filters"]) == 2


def test_get_by_id_owner_access(test_user, test_db):
    """Test that owner can access their collection."""
    user = test_user["user"]

    # Create collection
    data = {"name": "Test", "type": "manual"}
    collection = collection_service.create(test_db, user, data)

    # Get collection
    retrieved = collection_service.get_by_id(test_db, collection.id, user)

    assert retrieved.id == collection.id
    assert retrieved.owner_id == user.id


def test_get_by_id_collaborator_access(test_user, test_other_user, test_db):
    """Test that accepted collaborator can access collection."""
    owner = test_user["user"]
    collaborator = test_other_user["user"]

    # Create collection
    data = {"name": "Shared", "type": "manual"}
    collection = collection_service.create(test_db, owner, data)

    # Add collaborator
    collab = Collaborator(
        collection_id=collection.id,
        user_id=collaborator.id,
        role="editor",
    )
    from datetime import datetime, timezone
    collab.accepted_at = datetime.now(timezone.utc)
    test_db.add(collab)
    test_db.commit()

    # Collaborator should be able to access
    retrieved = collection_service.get_by_id(test_db, collection.id, collaborator)

    assert retrieved.id == collection.id


def test_get_by_id_no_access(test_user, test_other_user, test_db):
    """Test that non-owner/non-collaborator gets 403."""
    owner = test_user["user"]
    other = test_other_user["user"]

    # Create collection
    data = {"name": "Private", "type": "manual"}
    collection = collection_service.create(test_db, owner, data)

    # Other user should not have access
    with pytest.raises(HTTPException) as exc_info:
        collection_service.get_by_id(test_db, collection.id, other)

    assert exc_info.value.status_code == 403


def test_get_by_id_not_found(test_user, test_db):
    """Test that non-existent collection returns 404."""
    user = test_user["user"]

    with pytest.raises(HTTPException) as exc_info:
        collection_service.get_by_id(test_db, "nonexistent", user)

    assert exc_info.value.status_code == 404


def test_list_for_user_owned(test_user, test_db):
    """Test listing owned collections."""
    user = test_user["user"]

    # Create two collections
    collection_service.create(test_db, user, {"name": "Collection 1", "type": "manual"})
    collection_service.create(test_db, user, {"name": "Collection 2", "type": "manual"})

    collections = collection_service.list_for_user(test_db, user)

    assert len(collections) == 2


def test_list_for_user_collaborated(test_user, test_other_user, test_db):
    """Test listing includes collaborated collections."""
    owner = test_user["user"]
    collaborator = test_other_user["user"]

    # Owner creates collection
    collection = collection_service.create(test_db, owner, {"name": "Shared", "type": "manual"})

    # Add collaborator
    collab = Collaborator(
        collection_id=collection.id,
        user_id=collaborator.id,
        role="editor",
    )
    from datetime import datetime, timezone
    collab.accepted_at = datetime.now(timezone.utc)
    test_db.add(collab)
    test_db.commit()

    # Collaborator should see the collection
    collections = collection_service.list_for_user(test_db, collaborator)

    assert len(collections) == 1
    assert collections[0].id == collection.id


def test_update_collection_owner_only(test_user, test_other_user, test_db):
    """Test that only owner can update collection."""
    owner = test_user["user"]
    other = test_other_user["user"]

    # Create collection
    collection = collection_service.create(test_db, owner, {"name": "Original", "type": "manual"})

    # Owner can update
    updated = collection_service.update(test_db, collection, owner, {"name": "Updated"})
    assert updated.name == "Updated"

    # Non-owner gets 403
    with pytest.raises(HTTPException) as exc_info:
        collection_service.update(test_db, collection, other, {"name": "Hacked"})

    assert exc_info.value.status_code == 403


def test_delete_collection_owner_only(test_user, test_other_user, test_db):
    """Test that only owner can delete collection."""
    owner = test_user["user"]
    other = test_other_user["user"]

    # Create collection
    collection = collection_service.create(test_db, owner, {"name": "To Delete", "type": "manual"})
    collection_id = collection.id

    # Non-owner gets 403
    with pytest.raises(HTTPException) as exc_info:
        collection_service.delete(test_db, collection, other)

    assert exc_info.value.status_code == 403

    # Owner can delete
    collection_service.delete(test_db, collection, owner)

    # Verify it's deleted
    deleted = test_db.query(Collection).filter(Collection.id == collection_id).first()
    assert deleted is None


def test_add_recipes_owned_by_collection_owner(test_user, test_recipe, test_db):
    """Test adding recipe owned by collection owner (no duplication)."""
    user = test_user["user"]

    # Create collection
    collection = collection_service.create(test_db, user, {"name": "My Recipes", "type": "manual"})

    # Add recipe (owned by same user)
    collection_service.add_recipes(test_db, collection, user, [test_recipe.id])

    # Check recipe was added (not duplicated)
    memberships = test_db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id
    ).all()

    assert len(memberships) == 1
    assert memberships[0].recipe_id == test_recipe.id

    # Check no new recipe was created
    recipe_count = test_db.query(Recipe).count()
    assert recipe_count == 1  # Only the original test_recipe


def test_add_recipes_duplicates_if_not_owned(test_user, test_other_user, test_recipe, test_db):
    """
    CRITICAL TEST: Auto-duplicate recipe when adding to collection owned by different user.
    """
    owner = test_user["user"]
    other = test_other_user["user"]

    # test_recipe is owned by test_user
    assert test_recipe.owner_id == owner.id

    # Other user creates a collection
    collection = collection_service.create(test_db, other, {"name": "Other's Collection", "type": "manual"})
    assert collection.owner_id == other.id

    # Other user adds test_recipe to their collection
    # This should duplicate the recipe because recipe owner != collection owner
    collection_service.add_recipes(test_db, collection, other, [test_recipe.id])

    # Check that a NEW recipe was created
    all_recipes = test_db.query(Recipe).all()
    assert len(all_recipes) == 2  # Original + duplicate

    # Find the duplicated recipe
    duplicated = next((r for r in all_recipes if r.id != test_recipe.id), None)
    assert duplicated is not None
    assert duplicated.owner_id == other.id  # Owned by collection owner
    assert duplicated.title == test_recipe.title  # Same content
    assert duplicated.cuisine == test_recipe.cuisine

    # Check that collection contains the DUPLICATED recipe, not original
    memberships = test_db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id
    ).all()

    assert len(memberships) == 1
    assert memberships[0].recipe_id == duplicated.id


def test_add_recipes_editor_permission(test_user, test_other_user, test_recipe, test_db):
    """Test that editor collaborator can add recipes."""
    owner = test_user["user"]
    editor = test_other_user["user"]

    # Create collection
    collection = collection_service.create(test_db, owner, {"name": "Shared", "type": "manual"})

    # Add editor collaborator
    collab = Collaborator(
        collection_id=collection.id,
        user_id=editor.id,
        role="editor",
    )
    from datetime import datetime, timezone
    collab.accepted_at = datetime.now(timezone.utc)
    test_db.add(collab)
    test_db.commit()

    # Editor should be able to add recipes
    collection_service.add_recipes(test_db, collection, editor, [test_recipe.id])

    memberships = test_db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id
    ).all()

    assert len(memberships) == 1


def test_add_recipes_viewer_denied(test_user, test_other_user, test_recipe, test_db):
    """Test that viewer collaborator cannot add recipes."""
    owner = test_user["user"]
    viewer = test_other_user["user"]

    # Create collection
    collection = collection_service.create(test_db, owner, {"name": "Shared", "type": "manual"})

    # Add viewer collaborator
    collab = Collaborator(
        collection_id=collection.id,
        user_id=viewer.id,
        role="viewer",
    )
    from datetime import datetime, timezone
    collab.accepted_at = datetime.now(timezone.utc)
    test_db.add(collab)
    test_db.commit()

    # Viewer should get 403
    with pytest.raises(HTTPException) as exc_info:
        collection_service.add_recipes(test_db, collection, viewer, [test_recipe.id])

    assert exc_info.value.status_code == 403


def test_remove_recipe_from_collection(test_user, test_recipe, test_db):
    """Test removing recipe from collection."""
    user = test_user["user"]

    # Create collection with recipe
    data = {"name": "Test", "type": "manual", "recipe_ids": [test_recipe.id]}
    collection = collection_service.create(test_db, user, data)

    # Remove recipe
    collection_service.remove_recipe(test_db, collection, user, test_recipe.id)

    # Check recipe was removed
    memberships = test_db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id
    ).all()

    assert len(memberships) == 0


def test_remove_recipe_not_in_collection(test_user, test_recipe, test_db):
    """Test removing recipe that's not in collection returns 404."""
    user = test_user["user"]

    # Create empty collection
    collection = collection_service.create(test_db, user, {"name": "Empty", "type": "manual"})

    # Try to remove recipe that's not in collection
    with pytest.raises(HTTPException) as exc_info:
        collection_service.remove_recipe(test_db, collection, user, test_recipe.id)

    assert exc_info.value.status_code == 404


def test_reorder_recipes(test_user, test_db):
    """Test reordering recipes in collection."""
    user = test_user["user"]

    # Create 3 recipes
    recipe1 = Recipe(owner_id=user.id, title="Recipe 1", source_type="manual", base_servings=4)
    recipe2 = Recipe(owner_id=user.id, title="Recipe 2", source_type="manual", base_servings=4)
    recipe3 = Recipe(owner_id=user.id, title="Recipe 3", source_type="manual", base_servings=4)
    test_db.add_all([recipe1, recipe2, recipe3])
    test_db.commit()

    # Create collection with recipes in order 1,2,3
    data = {
        "name": "Test",
        "type": "manual",
        "recipe_ids": [recipe1.id, recipe2.id, recipe3.id]
    }
    collection = collection_service.create(test_db, user, data)

    # Reorder to 3,1,2
    collection_service.reorder_recipes(test_db, collection, user, [recipe3.id, recipe1.id, recipe2.id])

    # Check new order
    memberships = test_db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id
    ).order_by(CollectionRecipe.sort_order).all()

    assert memberships[0].recipe_id == recipe3.id
    assert memberships[0].sort_order == 0
    assert memberships[1].recipe_id == recipe1.id
    assert memberships[1].sort_order == 1
    assert memberships[2].recipe_id == recipe2.id
    assert memberships[2].sort_order == 2


def test_get_recipes_manual_collection(test_user, test_recipe, test_db):
    """Test getting recipes from manual collection."""
    user = test_user["user"]

    # Create collection with recipe
    data = {"name": "Test", "type": "manual", "recipe_ids": [test_recipe.id]}
    collection = collection_service.create(test_db, user, data)

    # Get recipes
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert len(recipes) == 1
    assert recipes[0].id == test_recipe.id


def test_resolve_smart_collection_cuisine_filter(test_user, test_db):
    """Test smart collection with cuisine filter."""
    user = test_user["user"]

    # Create Italian and Mexican recipes
    italian = Recipe(owner_id=user.id, title="Pasta", cuisine="Italian", source_type="manual", base_servings=4)
    mexican = Recipe(owner_id=user.id, title="Tacos", cuisine="Mexican", source_type="manual", base_servings=4)
    test_db.add_all([italian, mexican])
    test_db.commit()

    # Create smart collection for Italian recipes
    data = {
        "name": "Italian Only",
        "type": "smart",
        "smart_rule": {
            "filters": [{"field": "cuisine", "operator": "equals", "value": "Italian"}]
        }
    }
    collection = collection_service.create(test_db, user, data)

    # Get recipes
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert len(recipes) == 1
    assert recipes[0].id == italian.id


def test_resolve_smart_collection_tags_filter(test_user, test_db):
    """Test smart collection with tags filter."""
    user = test_user["user"]

    # Create recipes with different tags
    quick = Recipe(owner_id=user.id, title="Quick Meal", tags=["quick", "easy"], source_type="manual", base_servings=4)
    slow = Recipe(owner_id=user.id, title="Slow Cook", tags=["slow"], source_type="manual", base_servings=4)
    test_db.add_all([quick, slow])
    test_db.commit()

    # Create smart collection for quick recipes
    data = {
        "name": "Quick Recipes",
        "type": "smart",
        "smart_rule": {
            "filters": [{"field": "tags", "operator": "contains", "value": "quick"}]
        }
    }
    collection = collection_service.create(test_db, user, data)

    # Get recipes
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert len(recipes) == 1
    assert recipes[0].id == quick.id


def test_resolve_smart_collection_difficulty_filter(test_user, test_db):
    """Test smart collection with difficulty filter."""
    user = test_user["user"]

    # Create recipes with different difficulties
    easy = Recipe(owner_id=user.id, title="Easy Recipe", difficulty="easy", source_type="manual", base_servings=4)
    hard = Recipe(owner_id=user.id, title="Hard Recipe", difficulty="hard", source_type="manual", base_servings=4)
    test_db.add_all([easy, hard])
    test_db.commit()

    # Create smart collection for easy recipes
    data = {
        "name": "Easy Recipes",
        "type": "smart",
        "smart_rule": {
            "filters": [{"field": "difficulty", "operator": "equals", "value": "easy"}]
        }
    }
    collection = collection_service.create(test_db, user, data)

    # Get recipes
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert len(recipes) == 1
    assert recipes[0].id == easy.id


def test_resolve_smart_collection_time_filter(test_user, test_db):
    """Test smart collection with time filters."""
    user = test_user["user"]

    # Create recipes with different times
    quick = Recipe(owner_id=user.id, title="Quick", total_time=20, source_type="manual", base_servings=4)
    medium = Recipe(owner_id=user.id, title="Medium", total_time=45, source_type="manual", base_servings=4)
    slow = Recipe(owner_id=user.id, title="Slow", total_time=120, source_type="manual", base_servings=4)
    test_db.add_all([quick, medium, slow])
    test_db.commit()

    # Create smart collection for recipes <= 30 minutes
    data = {
        "name": "Quick Meals",
        "type": "smart",
        "smart_rule": {
            "filters": [{"field": "total_time", "operator": "lte", "value": 30}]
        }
    }
    collection = collection_service.create(test_db, user, data)

    # Get recipes
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert len(recipes) == 1
    assert recipes[0].id == quick.id


def test_resolve_smart_collection_multiple_filters(test_user, test_db):
    """Test smart collection with multiple combined filters."""
    user = test_user["user"]

    # Create various recipes
    match = Recipe(
        owner_id=user.id,
        title="Perfect Match",
        cuisine="Italian",
        tags=["quick"],
        difficulty="easy",
        total_time=25,
        source_type="manual",
        base_servings=4
    )
    no_match = Recipe(
        owner_id=user.id,
        title="No Match",
        cuisine="Mexican",
        tags=["slow"],
        difficulty="hard",
        total_time=90,
        source_type="manual",
        base_servings=4
    )
    test_db.add_all([match, no_match])
    test_db.commit()

    # Create smart collection with multiple filters
    data = {
        "name": "Quick Easy Italian",
        "type": "smart",
        "smart_rule": {
            "filters": [
                {"field": "cuisine", "operator": "equals", "value": "Italian"},
                {"field": "tags", "operator": "contains", "value": "quick"},
                {"field": "difficulty", "operator": "equals", "value": "easy"},
                {"field": "total_time", "operator": "lte", "value": 30}
            ]
        }
    }
    collection = collection_service.create(test_db, user, data)

    # Get recipes
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert len(recipes) == 1
    assert recipes[0].id == match.id


def test_resolve_smart_collection_sorting(test_user, test_db):
    """Test smart collection sorting."""
    user = test_user["user"]

    # Create recipes
    zebra = Recipe(owner_id=user.id, title="Zebra Cake", total_time=60, source_type="manual", base_servings=4)
    apple = Recipe(owner_id=user.id, title="Apple Pie", total_time=45, source_type="manual", base_servings=4)
    banana = Recipe(owner_id=user.id, title="Banana Bread", total_time=30, source_type="manual", base_servings=4)
    test_db.add_all([zebra, apple, banana])
    test_db.commit()

    # Test sorting by title
    data = {
        "name": "Sorted by Title",
        "type": "smart",
        "smart_rule": {
            "filters": [],
            "sort": "title"
        }
    }
    collection = collection_service.create(test_db, user, data)
    recipes = collection_service.get_recipes(test_db, collection, user)

    assert recipes[0].title == "Apple Pie"
    assert recipes[1].title == "Banana Bread"
    assert recipes[2].title == "Zebra Cake"
