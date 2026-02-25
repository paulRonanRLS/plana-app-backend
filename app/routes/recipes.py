from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.recipe import Recipe, Ingredient, Step, Equipment, Nutrition, Pairing
from app.models.cook_log import CookLog
from app.schemas.recipe import (
    RecipeCreate, RecipeUpdate, RecipeResponse, RecipeListItem,
    RecipeListResponse, NoteCreate, CookSummary,
    IngredientResponse, StepResponse, EquipmentResponse,
    NutritionResponse, PairingResponse,
)

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _build_recipe_response(recipe: Recipe, db: Session) -> RecipeResponse:
    """Build a full RecipeResponse with cook summary."""
    # Cook summary
    logs = db.query(CookLog).filter(CookLog.recipe_id == recipe.id).all()
    cook_summary = None
    if logs:
        ratings = [log.rating for log in logs if log.rating]
        cook_summary = CookSummary(
            times_cooked=len(logs),
            avg_rating=round(sum(ratings) / len(ratings), 1) if ratings else None,
            last_cooked_at=max(log.cooked_at for log in logs),
        )

    return RecipeResponse(
        id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        cover_image_url=recipe.cover_image_url,
        source_type=recipe.source_type,
        source_url=recipe.source_url,
        source_attribution=recipe.source_attribution,
        cuisine=recipe.cuisine,
        tags=recipe.tags,
        difficulty=recipe.difficulty,
        prep_time=recipe.prep_time,
        cook_time=recipe.cook_time,
        total_time=recipe.total_time,
        base_servings=recipe.base_servings,
        notes=recipe.notes,
        ingredients=[IngredientResponse.model_validate(i) for i in recipe.ingredients],
        steps=[StepResponse.model_validate(s) for s in recipe.steps],
        equipment=[EquipmentResponse.model_validate(e) for e in recipe.equipment],
        nutrition=NutritionResponse.model_validate(recipe.nutrition) if recipe.nutrition else None,
        pairing=PairingResponse.model_validate(recipe.pairing) if recipe.pairing else None,
        cook_summary=cook_summary,
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


@router.post("", response_model=RecipeResponse, status_code=201)
def create_recipe(
    body: RecipeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new recipe with nested ingredients, steps, equipment."""
    recipe = Recipe(
        owner_id=current_user.id,
        title=body.title,
        description=body.description,
        cover_image_url=body.cover_image_url,
        source_type=body.source_type,
        source_url=body.source_url,
        source_attribution=body.source_attribution,
        cuisine=body.cuisine,
        tags=body.tags,
        difficulty=body.difficulty,
        prep_time=body.prep_time,
        cook_time=body.cook_time,
        total_time=body.total_time,
        base_servings=body.base_servings,
    )

    # Nested entities
    for ing in body.ingredients:
        recipe.ingredients.append(Ingredient(**ing.model_dump()))

    for step in body.steps:
        recipe.steps.append(Step(**step.model_dump()))

    for equip in body.equipment:
        recipe.equipment.append(Equipment(**equip.model_dump()))

    if body.nutrition:
        recipe.nutrition = Nutrition(**body.nutrition.model_dump())

    if body.pairing:
        recipe.pairing = Pairing(**body.pairing.model_dump())

    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    return _build_recipe_response(recipe, db)


@router.get("", response_model=RecipeListResponse)
def list_recipes(
    q: str | None = None,
    cuisine: str | None = None,
    tags: str | None = None,
    difficulty: str | None = None,
    max_time: int | None = None,
    sort: str = "created_at",
    limit: int = Query(default=20, le=50),
    cursor: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List user's recipes with search, filtering, sorting, and pagination."""
    query = db.query(Recipe).filter(Recipe.owner_id == current_user.id)

    # Search
    if q:
        search_term = f"%{q}%"
        query = query.filter(
            Recipe.title.ilike(search_term)
            | Recipe.description.ilike(search_term)
        )

    # Filters
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

    # Sort
    sort_map = {
        "created_at": Recipe.created_at.desc(),
        "title": Recipe.title.asc(),
        "total_time": Recipe.total_time.asc(),
    }
    query = query.order_by(sort_map.get(sort, Recipe.created_at.desc()))

    # Cursor-based pagination (using created_at as cursor)
    if cursor:
        from datetime import datetime
        import base64
        try:
            cursor_dt = datetime.fromisoformat(base64.b64decode(cursor).decode())
            query = query.filter(Recipe.created_at < cursor_dt)
        except Exception:
            pass  # Invalid cursor, ignore

    recipes = query.limit(limit + 1).all()  # Fetch one extra to check has_more
    has_more = len(recipes) > limit
    recipes = recipes[:limit]

    # Build list items with cook stats
    items = []
    for r in recipes:
        log_count = db.query(func.count(CookLog.id)).filter(CookLog.recipe_id == r.id).scalar()
        avg_rating = db.query(func.avg(CookLog.rating)).filter(CookLog.recipe_id == r.id).scalar()
        items.append(RecipeListItem(
            id=r.id,
            title=r.title,
            cover_image_url=r.cover_image_url,
            cuisine=r.cuisine,
            difficulty=r.difficulty,
            total_time=r.total_time,
            tags=r.tags,
            avg_rating=round(float(avg_rating), 1) if avg_rating else None,
            times_cooked=log_count or 0,
            created_at=r.created_at,
        ))

    # Generate next cursor
    import base64
    next_cursor = None
    if has_more and recipes:
        next_cursor = base64.b64encode(recipes[-1].created_at.isoformat().encode()).decode()

    return RecipeListResponse(
        recipes=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_count=total_count,
    )


@router.get("/{recipe_id}", response_model=RecipeResponse)
def get_recipe(
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full recipe detail with all nested data."""
    recipe = (
        db.query(Recipe)
        .options(
            joinedload(Recipe.ingredients),
            joinedload(Recipe.steps),
            joinedload(Recipe.equipment),
            joinedload(Recipe.nutrition),
            joinedload(Recipe.pairing),
        )
        .filter(Recipe.id == recipe_id, Recipe.owner_id == current_user.id)
        .first()
    )
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _build_recipe_response(recipe, db)


@router.patch("/{recipe_id}", response_model=RecipeResponse)
def update_recipe(
    recipe_id: str,
    body: RecipeUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update a recipe. Accepts partial updates.
    When updating ingredients/steps/equipment, send the full array — the backend replaces them.
    """
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == current_user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    update_data = body.model_dump(exclude_unset=True)

    # Handle nested replacements
    if "ingredients" in update_data:
        # Delete existing and replace
        db.query(Ingredient).filter(Ingredient.recipe_id == recipe_id).delete()
        for ing in body.ingredients:
            db.add(Ingredient(recipe_id=recipe_id, **ing.model_dump()))
        del update_data["ingredients"]

    if "steps" in update_data:
        db.query(Step).filter(Step.recipe_id == recipe_id).delete()
        for step in body.steps:
            db.add(Step(recipe_id=recipe_id, **step.model_dump()))
        del update_data["steps"]

    if "equipment" in update_data:
        db.query(Equipment).filter(Equipment.recipe_id == recipe_id).delete()
        for equip in body.equipment:
            db.add(Equipment(recipe_id=recipe_id, **equip.model_dump()))
        del update_data["equipment"]

    if "nutrition" in update_data:
        if recipe.nutrition:
            db.delete(recipe.nutrition)
        if body.nutrition:
            db.add(Nutrition(recipe_id=recipe_id, **body.nutrition.model_dump()))
        del update_data["nutrition"]

    if "pairing" in update_data:
        if recipe.pairing:
            db.delete(recipe.pairing)
        if body.pairing:
            db.add(Pairing(recipe_id=recipe_id, **body.pairing.model_dump()))
        del update_data["pairing"]

    # Update scalar fields
    for field, value in update_data.items():
        setattr(recipe, field, value)

    db.commit()
    db.refresh(recipe)
    return _build_recipe_response(recipe, db)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a recipe and all associated data."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == current_user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    db.delete(recipe)
    db.commit()


@router.post("/{recipe_id}/notes", response_model=RecipeResponse)
def add_note(
    recipe_id: str,
    body: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append a note to a recipe."""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == current_user.id).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if recipe.notes:
        recipe.notes = recipe.notes + "\n" + body.text
    else:
        recipe.notes = body.text

    db.commit()
    db.refresh(recipe)
    return _build_recipe_response(recipe, db)
