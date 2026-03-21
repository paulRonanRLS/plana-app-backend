"""
Recipe endpoints - CRUD operations for recipes.

This router is a thin orchestration layer that delegates business logic to the service layer.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.cook_log import CookLog
from app.schemas.recipe import (
    RecipeCreate, RecipeUpdate, RecipeResponse, RecipeListItem,
    RecipeListIngredient, RecipeListResponse, NoteCreate, CookSummary,
    IngredientResponse, StepResponse, EquipmentResponse,
    NutritionResponse, PairingResponse,
)
from app.services import recipe_service

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _build_recipe_response(recipe, db: Session) -> RecipeResponse:
    """Build a full RecipeResponse with cook summary."""
    # Get cook summary from service
    cook_summary_data = recipe_service.get_cook_summary(db, recipe.id)
    cook_summary = CookSummary(**cook_summary_data) if cook_summary_data else None

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
    recipe_data = body.model_dump()
    recipe = recipe_service.create(db, current_user.id, recipe_data)
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
    recipes, next_cursor, has_more, total_count = recipe_service.list_recipes(
        db=db,
        owner_id=current_user.id,
        search_query=q,
        cuisine=cuisine,
        tags=tags,
        difficulty=difficulty,
        max_time=max_time,
        sort=sort,
        limit=limit,
        cursor=cursor,
    )

    # Build list items with cook stats
    items = []
    for r in recipes:
        log_count = db.query(func.count(CookLog.id)).filter(CookLog.recipe_id == r.id).scalar()
        avg_rating = db.query(func.avg(CookLog.rating)).filter(CookLog.recipe_id == r.id).scalar()
        items.append(
            RecipeListItem(
                id=r.id,
                title=r.title,
                cover_image_url=r.cover_image_url,
                cuisine=r.cuisine,
                difficulty=r.difficulty,
                total_time=r.total_time,
                tags=r.tags,
                ingredients=[RecipeListIngredient(id=i.id, name=i.name) for i in r.ingredients],
                avg_rating=round(float(avg_rating), 1) if avg_rating else None,
                times_cooked=log_count or 0,
                created_at=r.created_at,
            )
        )

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
    recipe = recipe_service.get_by_id(db, recipe_id, current_user.id)
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
    update_data = body.model_dump(exclude_unset=True)
    recipe = recipe_service.update(db, recipe_id, current_user.id, update_data)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _build_recipe_response(recipe, db)


@router.delete("/{recipe_id}", status_code=204)
def delete_recipe(
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a recipe and all associated data."""
    success = recipe_service.delete(db, recipe_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Recipe not found")


@router.post("/{recipe_id}/notes", response_model=RecipeResponse)
def add_note(
    recipe_id: str,
    body: NoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Append a note to a recipe."""
    recipe = recipe_service.add_note(db, recipe_id, current_user.id, body.text)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return _build_recipe_response(recipe, db)
