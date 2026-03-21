"""
Recipe service for business logic operations.

Handles all recipe CRUD operations and related business logic.
"""

from sqlalchemy.orm import Session, joinedload, subqueryload
from sqlalchemy import func

from app.models.recipe import Recipe, Ingredient, Step, Equipment, Nutrition, Pairing
from app.models.cook_log import CookLog


def create(db: Session, owner_id: str, recipe_data: dict) -> Recipe:
    """
    Create a new recipe with nested entities.

    Args:
        db: Database session
        owner_id: ID of the user creating the recipe
        recipe_data: Dictionary containing recipe data including nested ingredients, steps, etc.

    Returns:
        Created Recipe object with all nested entities
    """
    # Extract nested data
    ingredients_data = recipe_data.pop("ingredients", [])
    steps_data = recipe_data.pop("steps", [])
    equipment_data = recipe_data.pop("equipment", [])
    nutrition_data = recipe_data.pop("nutrition", None)
    pairing_data = recipe_data.pop("pairing", None)

    # Create recipe
    recipe = Recipe(owner_id=owner_id, **recipe_data)

    # Add nested entities
    for ing_data in ingredients_data:
        recipe.ingredients.append(Ingredient(**ing_data))

    for step_data in steps_data:
        recipe.steps.append(Step(**step_data))

    for equip_data in equipment_data:
        recipe.equipment.append(Equipment(**equip_data))

    if nutrition_data:
        recipe.nutrition = Nutrition(**nutrition_data)

    if pairing_data:
        recipe.pairing = Pairing(**pairing_data)

    db.add(recipe)
    db.commit()
    db.refresh(recipe)

    return recipe


def get_by_id(db: Session, recipe_id: str, owner_id: str) -> Recipe | None:
    """
    Retrieve a recipe by ID with ownership check.

    Args:
        db: Database session
        recipe_id: Recipe ID to look up
        owner_id: ID of the user making the request (for ownership verification)

    Returns:
        Recipe object if found and owned by user, None otherwise
    """
    return (
        db.query(Recipe)
        .options(
            joinedload(Recipe.ingredients),
            joinedload(Recipe.steps),
            joinedload(Recipe.equipment),
            joinedload(Recipe.nutrition),
            joinedload(Recipe.pairing),
        )
        .filter(Recipe.id == recipe_id, Recipe.owner_id == owner_id)
        .first()
    )


def list_recipes(
    db: Session,
    owner_id: str,
    search_query: str | None = None,
    cuisine: str | None = None,
    tags: str | None = None,
    difficulty: str | None = None,
    max_time: int | None = None,
    sort: str = "created_at",
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[Recipe], str | None, bool, int]:
    """
    List recipes with filtering, sorting, and pagination.

    Args:
        db: Database session
        owner_id: ID of the user whose recipes to list
        search_query: Search term for title/description
        cuisine: Filter by cuisine
        tags: Comma-separated tags to filter by
        difficulty: Filter by difficulty level
        max_time: Filter by maximum total time
        sort: Sort field (created_at, title, total_time)
        limit: Maximum number of results
        cursor: Pagination cursor

    Returns:
        Tuple of (recipes list, next_cursor, has_more, total_count)
    """
    query = db.query(Recipe).options(subqueryload(Recipe.ingredients)).filter(Recipe.owner_id == owner_id)

    # Apply filters
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            Recipe.title.ilike(search_term) | Recipe.description.ilike(search_term)
        )

    if cuisine:
        query = query.filter(Recipe.cuisine.ilike(cuisine))

    if difficulty:
        query = query.filter(Recipe.difficulty == difficulty)

    if max_time:
        query = query.filter(Recipe.total_time <= max_time)

    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        query = query.filter(Recipe.tags.overlap(tag_list))

    # Get total count before pagination
    total_count = query.count()

    # Apply sorting
    sort_map = {
        "created_at": Recipe.created_at.desc(),
        "title": Recipe.title.asc(),
        "total_time": Recipe.total_time.asc(),
    }
    query = query.order_by(sort_map.get(sort, Recipe.created_at.desc()))

    # Cursor-based pagination
    if cursor:
        from datetime import datetime
        import base64

        try:
            cursor_dt = datetime.fromisoformat(base64.b64decode(cursor).decode())
            query = query.filter(Recipe.created_at < cursor_dt)
        except Exception:
            pass  # Invalid cursor, ignore

    # Fetch one extra to check if there are more results
    recipes = query.limit(limit + 1).all()
    has_more = len(recipes) > limit
    recipes = recipes[:limit]

    # Generate next cursor
    import base64

    next_cursor = None
    if has_more and recipes:
        next_cursor = base64.b64encode(recipes[-1].created_at.isoformat().encode()).decode()

    return recipes, next_cursor, has_more, total_count


def update(db: Session, recipe_id: str, owner_id: str, update_data: dict) -> Recipe | None:
    """
    Update a recipe with partial data.

    Handles both scalar field updates and nested entity replacements.
    When updating nested arrays (ingredients, steps, equipment), the entire
    array is replaced.

    Args:
        db: Database session
        recipe_id: Recipe ID to update
        owner_id: ID of the user making the request (for ownership verification)
        update_data: Dictionary of fields to update

    Returns:
        Updated Recipe object if found and owned by user, None otherwise
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == owner_id).first()

    if not recipe:
        return None

    # Handle nested entity replacements
    if "ingredients" in update_data:
        db.query(Ingredient).filter(Ingredient.recipe_id == recipe_id).delete()
        for ing_data in update_data.pop("ingredients"):
            db.add(Ingredient(recipe_id=recipe_id, **ing_data))

    if "steps" in update_data:
        db.query(Step).filter(Step.recipe_id == recipe_id).delete()
        for step_data in update_data.pop("steps"):
            db.add(Step(recipe_id=recipe_id, **step_data))

    if "equipment" in update_data:
        db.query(Equipment).filter(Equipment.recipe_id == recipe_id).delete()
        for equip_data in update_data.pop("equipment"):
            db.add(Equipment(recipe_id=recipe_id, **equip_data))

    if "nutrition" in update_data:
        if recipe.nutrition:
            db.delete(recipe.nutrition)
        nutrition_data = update_data.pop("nutrition")
        if nutrition_data:
            db.add(Nutrition(recipe_id=recipe_id, **nutrition_data))

    if "pairing" in update_data:
        if recipe.pairing:
            db.delete(recipe.pairing)
        pairing_data = update_data.pop("pairing")
        if pairing_data:
            db.add(Pairing(recipe_id=recipe_id, **pairing_data))

    # Update scalar fields
    for field, value in update_data.items():
        setattr(recipe, field, value)

    db.commit()
    db.refresh(recipe)

    return recipe


def delete(db: Session, recipe_id: str, owner_id: str) -> bool:
    """
    Delete a recipe and all associated data.

    Args:
        db: Database session
        recipe_id: Recipe ID to delete
        owner_id: ID of the user making the request (for ownership verification)

    Returns:
        True if recipe was deleted, False if not found or not owned by user
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == owner_id).first()

    if not recipe:
        return False

    db.delete(recipe)
    db.commit()
    return True


def add_note(db: Session, recipe_id: str, owner_id: str, note_text: str) -> Recipe | None:
    """
    Append a note to a recipe's notes field.

    Args:
        db: Database session
        recipe_id: Recipe ID to add note to
        owner_id: ID of the user making the request (for ownership verification)
        note_text: Note text to append

    Returns:
        Updated Recipe object if found and owned by user, None otherwise
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == owner_id).first()

    if not recipe:
        return None

    if recipe.notes:
        recipe.notes = recipe.notes + "\n" + note_text
    else:
        recipe.notes = note_text

    db.commit()
    db.refresh(recipe)

    return recipe


def get_cook_summary(db: Session, recipe_id: str) -> dict | None:
    """
    Get cooking statistics summary for a recipe.

    Args:
        db: Database session
        recipe_id: Recipe ID to get stats for

    Returns:
        Dictionary with times_cooked, avg_rating, last_cooked_at or None if no logs
    """
    logs = db.query(CookLog).filter(CookLog.recipe_id == recipe_id).all()

    if not logs:
        return None

    ratings = [log.rating for log in logs if log.rating]

    return {
        "times_cooked": len(logs),
        "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "last_cooked_at": max(log.cooked_at for log in logs),
    }
