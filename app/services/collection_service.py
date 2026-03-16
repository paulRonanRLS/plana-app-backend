"""
Collection service for business logic operations.

Handles collection CRUD, membership management, permissions, and smart collections.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, String, cast

from app.models.collection import Collection, CollectionRecipe, Collaborator, CollectionInvite
from app.models.recipe import Recipe, Ingredient, Step, Equipment, Nutrition, Pairing
from app.models.user import User


def create(db: Session, user: User, data: dict) -> Collection:
    """
    Create a new collection.

    Args:
        db: Database session
        user: User creating the collection
        data: Collection data (name, description, cover, type, smart_rule, recipe_ids)

    Returns:
        Created Collection object
    """
    recipe_ids = data.pop("recipe_ids", [])

    collection = Collection(
        owner_id=user.id,
        **data
    )

    db.add(collection)
    db.flush()  # Get collection ID before adding recipes

    # Add initial recipes for manual collections
    if collection.type == "manual" and recipe_ids:
        for i, recipe_id in enumerate(recipe_ids):
            # Only add recipes owned by the user
            recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == user.id).first()
            if recipe:
                db.add(CollectionRecipe(
                    collection_id=collection.id,
                    recipe_id=recipe.id,
                    sort_order=i,
                    added_by=user.id,
                ))

    db.commit()
    db.refresh(collection)
    return collection


def get_by_id(db: Session, collection_id: str, user: User) -> Collection:
    """
    Get collection by ID with access check.

    Args:
        db: Database session
        collection_id: Collection ID
        user: User making the request

    Returns:
        Collection object

    Raises:
        HTTPException: 404 if not found, 403 if no access
    """
    collection = (
        db.query(Collection)
        .options(
            joinedload(Collection.recipe_memberships),
            joinedload(Collection.collaborators),
        )
        .filter(Collection.id == collection_id)
        .first()
    )

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Check access: owner or collaborator
    if collection.owner_id != user.id:
        is_collaborator = db.query(Collaborator).filter(
            Collaborator.collection_id == collection_id,
            Collaborator.user_id == user.id,
            Collaborator.accepted_at.isnot(None),
        ).first()

        if not is_collaborator:
            raise HTTPException(status_code=403, detail="Access denied")

    return collection


def list_for_user(db: Session, user: User) -> list[Collection]:
    """
    List all collections owned by or shared with the user.

    Args:
        db: Database session
        user: User making the request

    Returns:
        List of Collection objects
    """
    # Owned collections
    owned = db.query(Collection).filter(Collection.owner_id == user.id).all()

    # Collaborated collections
    collab_collection_ids = (
        db.query(Collaborator.collection_id)
        .filter(
            Collaborator.user_id == user.id,
            Collaborator.accepted_at.isnot(None)
        )
        .all()
    )

    collaborated = []
    if collab_collection_ids:
        collaborated = (
            db.query(Collection)
            .filter(Collection.id.in_([c[0] for c in collab_collection_ids]))
            .all()
        )

    return owned + collaborated


def update(db: Session, collection: Collection, user: User, data: dict) -> Collection:
    """
    Update collection metadata.

    Args:
        db: Database session
        collection: Collection to update
        user: User making the request
        data: Dictionary of fields to update

    Returns:
        Updated Collection object

    Raises:
        HTTPException: 403 if user is not owner
    """
    # Owner only
    if collection.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can update this collection")

    for field, value in data.items():
        setattr(collection, field, value)

    db.commit()
    db.refresh(collection)
    return collection


def delete(db: Session, collection: Collection, user: User) -> None:
    """
    Delete a collection. Does not delete recipes.

    Args:
        db: Database session
        collection: Collection to delete
        user: User making the request

    Raises:
        HTTPException: 403 if user is not owner
    """
    # Owner only
    if collection.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete this collection")

    db.delete(collection)
    db.commit()


def _has_write_access(db: Session, collection: Collection, user: User) -> bool:
    """Check if user has write access (owner or editor collaborator)."""
    if collection.owner_id == user.id:
        return True

    collaborator = db.query(Collaborator).filter(
        Collaborator.collection_id == collection.id,
        Collaborator.user_id == user.id,
        Collaborator.accepted_at.isnot(None),
        Collaborator.role == "editor",
    ).first()

    return collaborator is not None


def _duplicate_recipe(db: Session, original_recipe: Recipe, new_owner_id: str) -> Recipe:
    """
    Create a duplicate of a recipe for a new owner.

    Args:
        db: Database session
        original_recipe: Recipe to duplicate
        new_owner_id: ID of the new owner

    Returns:
        Duplicated Recipe object
    """
    # Create new recipe with copied data
    new_recipe = Recipe(
        owner_id=new_owner_id,
        title=original_recipe.title,
        description=original_recipe.description,
        cover_image_url=original_recipe.cover_image_url,
        source_type=original_recipe.source_type,
        source_url=original_recipe.source_url,
        source_attribution=original_recipe.source_attribution,
        cuisine=original_recipe.cuisine,
        tags=original_recipe.tags,
        difficulty=original_recipe.difficulty,
        prep_time=original_recipe.prep_time,
        cook_time=original_recipe.cook_time,
        total_time=original_recipe.total_time,
        base_servings=original_recipe.base_servings,
        notes=original_recipe.notes,
    )

    # Copy nested entities
    for ing in original_recipe.ingredients:
        new_recipe.ingredients.append(Ingredient(
            name=ing.name,
            quantity=ing.quantity,
            unit=ing.unit,
            group_label=ing.group_label,
            is_optional=ing.is_optional,
            sort_order=ing.sort_order,
        ))

    for step in original_recipe.steps:
        new_recipe.steps.append(Step(
            step_number=step.step_number,
            instruction=step.instruction,
            timer_seconds=step.timer_seconds,
            section_label=step.section_label,
        ))

    for equip in original_recipe.equipment:
        new_recipe.equipment.append(Equipment(
            name=equip.name,
            is_essential=equip.is_essential,
        ))

    if original_recipe.nutrition:
        new_recipe.nutrition = Nutrition(
            calories=original_recipe.nutrition.calories,
            protein_g=original_recipe.nutrition.protein_g,
            carbs_g=original_recipe.nutrition.carbs_g,
            fat_g=original_recipe.nutrition.fat_g,
            fiber_g=original_recipe.nutrition.fiber_g,
            sugar_g=original_recipe.nutrition.sugar_g,
            source=original_recipe.nutrition.source,
            confidence=original_recipe.nutrition.confidence,
        )

    if original_recipe.pairing:
        new_recipe.pairing = Pairing(
            suggestion=original_recipe.pairing.suggestion,
            notes=original_recipe.pairing.notes,
        )

    db.add(new_recipe)
    db.flush()

    return new_recipe


def add_recipes(db: Session, collection: Collection, user: User, recipe_ids: list[str]) -> None:
    """
    Add recipes to a collection.

    If a recipe is not owned by the collection owner, it is duplicated first.

    Args:
        db: Database session
        collection: Collection to add recipes to
        user: User making the request
        recipe_ids: List of recipe IDs to add

    Raises:
        HTTPException: 403 if user doesn't have write access
    """
    # Check write access (owner or editor)
    if not _has_write_access(db, collection, user):
        raise HTTPException(status_code=403, detail="You don't have permission to add recipes to this collection")

    # Get current max sort_order
    max_order_row = (
        db.query(CollectionRecipe.sort_order)
        .filter(CollectionRecipe.collection_id == collection.id)
        .order_by(CollectionRecipe.sort_order.desc())
        .first()
    )
    next_order = (max_order_row[0] + 1) if max_order_row else 0

    for recipe_id in recipe_ids:
        # Check if already in collection
        existing = db.query(CollectionRecipe).filter(
            CollectionRecipe.collection_id == collection.id,
            CollectionRecipe.recipe_id == recipe_id,
        ).first()

        if existing:
            continue  # Skip if already in collection

        # Get the recipe
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()

        if not recipe:
            continue  # Skip if recipe doesn't exist

        # If recipe is not owned by collection owner, duplicate it
        if recipe.owner_id != collection.owner_id:
            recipe = _duplicate_recipe(db, recipe, collection.owner_id)

        # Add to collection
        db.add(CollectionRecipe(
            collection_id=collection.id,
            recipe_id=recipe.id,
            sort_order=next_order,
            added_by=user.id,
        ))
        next_order += 1

    db.commit()


def remove_recipe(db: Session, collection: Collection, user: User, recipe_id: str) -> None:
    """
    Remove a recipe from a collection.

    Args:
        db: Database session
        collection: Collection to remove recipe from
        user: User making the request
        recipe_id: Recipe ID to remove

    Raises:
        HTTPException: 403 if user doesn't have write access, 404 if recipe not in collection
    """
    # Check write access
    if not _has_write_access(db, collection, user):
        raise HTTPException(status_code=403, detail="You don't have permission to remove recipes from this collection")

    membership = db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection.id,
        CollectionRecipe.recipe_id == recipe_id,
    ).first()

    if not membership:
        raise HTTPException(status_code=404, detail="Recipe not in collection")

    db.delete(membership)
    db.commit()


def reorder_recipes(db: Session, collection: Collection, user: User, ordered_recipe_ids: list[str]) -> None:
    """
    Update the display order of recipes in a collection.

    Args:
        db: Database session
        collection: Collection to reorder
        user: User making the request
        ordered_recipe_ids: List of recipe IDs in desired order

    Raises:
        HTTPException: 403 if user doesn't have write access
    """
    # Check write access
    if not _has_write_access(db, collection, user):
        raise HTTPException(status_code=403, detail="You don't have permission to reorder this collection")

    for i, recipe_id in enumerate(ordered_recipe_ids):
        membership = db.query(CollectionRecipe).filter(
            CollectionRecipe.collection_id == collection.id,
            CollectionRecipe.recipe_id == recipe_id,
        ).first()

        if membership:
            membership.sort_order = i

    db.commit()


def get_recipes(db: Session, collection: Collection, user: User) -> list[Recipe]:
    """
    Get all recipes in a collection, ordered by sort_order.

    For smart collections, resolves the query dynamically.

    Args:
        db: Database session
        collection: Collection to get recipes from
        user: User making the request

    Returns:
        List of Recipe objects
    """
    if collection.type == "smart":
        return resolve_smart_collection(db, collection, user)

    # Manual collection - return recipes ordered by membership sort_order
    recipe_ids = [
        cm.recipe_id
        for cm in sorted(collection.recipe_memberships, key=lambda x: x.sort_order)
    ]

    if not recipe_ids:
        return []

    # Fetch recipes in order
    recipes = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()

    # Re-sort to match membership order
    recipe_map = {r.id: r for r in recipes}
    return [recipe_map[rid] for rid in recipe_ids if rid in recipe_map]


def resolve_smart_collection(db: Session, collection: Collection, user: User) -> list[Recipe]:
    """
    Resolve a smart collection by building a dynamic query from smart_rule JSON.

    Smart rule format:
    {
        "filters": [
            {"field": "cuisine", "operator": "equals", "value": "Italian"},
            {"field": "tags", "operator": "contains", "value": "quick"},
            {"field": "difficulty", "operator": "equals", "value": "easy"},
            {"field": "total_time", "operator": "lte", "value": 30},
        ],
        "sort": "created_at",  # created_at | title | total_time
        "limit": 50
    }

    Args:
        db: Database session
        collection: Collection with smart_rule
        user: User making the request (for ownership filtering)

    Returns:
        List of Recipe objects matching the smart rule
    """
    if not collection.smart_rule:
        return []

    # Start with base query for owner's recipes
    query = db.query(Recipe).filter(Recipe.owner_id == collection.owner_id)

    # Apply filters
    filters = collection.smart_rule.get("filters", [])
    for filter_rule in filters:
        field = filter_rule.get("field")
        operator = filter_rule.get("operator")
        value = filter_rule.get("value")

        if field == "cuisine":
            if operator == "equals":
                query = query.filter(Recipe.cuisine.ilike(value))

        elif field == "tags":
            # Check database dialect for appropriate query method
            is_sqlite = db.bind.dialect.name == "sqlite"

            if operator == "contains":
                # Check if value is in the tags array
                if is_sqlite:
                    # SQLite with JSON: search within JSON string
                    query = query.filter(cast(Recipe.tags, String).like(f'%"{value}"%'))
                else:
                    # PostgreSQL with ARRAY: use contains
                    query = query.filter(Recipe.tags.contains([value]))
            elif operator == "any_of":
                # Match any of the provided tags
                if is_sqlite:
                    # SQLite: check each tag individually
                    or_filters = [cast(Recipe.tags, String).like(f'%"{v}"%') for v in value]
                    query = query.filter(or_(*or_filters))
                else:
                    # PostgreSQL: use overlap
                    query = query.filter(Recipe.tags.overlap(value))

        elif field == "difficulty":
            if operator == "equals":
                query = query.filter(Recipe.difficulty == value)

        elif field == "total_time":
            if operator == "lte":
                query = query.filter(Recipe.total_time <= value)
            elif operator == "gte":
                query = query.filter(Recipe.total_time >= value)
            elif operator == "equals":
                query = query.filter(Recipe.total_time == value)

        elif field == "title":
            if operator == "contains":
                query = query.filter(Recipe.title.ilike(f"%{value}%"))

    # Apply sorting
    sort_field = collection.smart_rule.get("sort", "created_at")
    if sort_field == "title":
        query = query.order_by(Recipe.title.asc())
    elif sort_field == "total_time":
        query = query.order_by(Recipe.total_time.asc())
    else:  # created_at
        query = query.order_by(Recipe.created_at.desc())

    # Apply limit
    limit = collection.smart_rule.get("limit", 50)
    query = query.limit(limit)

    return query.all()
