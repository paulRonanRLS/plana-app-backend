from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.models.recipe import Recipe
from app.models.collection import Collection, CollectionRecipe, Collaborator
from app.schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionResponse, CollectionListItem,
    CollectionListResponse, CollectionRecipeItem, CollaboratorResponse, OwnerResponse,
    AddRecipesRequest, ReorderRecipesRequest, SmartCollectionCreate,
    SmartSuggestionsResponse, InviteRequest, InviteResponse,
    AcceptInviteRequest, UpdateRoleRequest, DuplicateResponse,
)

router = APIRouter(prefix="/collections", tags=["collections"])


def _build_collection_response(col: Collection, current_user_id: str, db: Session) -> CollectionResponse:
    """Build full collection response with recipes and collaborators."""
    owner = db.query(User).filter(User.id == col.owner_id).first()

    recipes = []
    for cm in col.recipe_memberships:
        recipe = db.query(Recipe).filter(Recipe.id == cm.recipe_id).first()
        if recipe:
            recipes.append(CollectionRecipeItem(
                id=recipe.id,
                title=recipe.title,
                cover_image_url=recipe.cover_image_url,
                cuisine=recipe.cuisine,
                total_time=recipe.total_time,
                sort_order=cm.sort_order,
            ))

    collabs = []
    for c in col.collaborators:
        user = db.query(User).filter(User.id == c.user_id).first()
        if user:
            collabs.append(CollaboratorResponse(
                user_id=user.id,
                name=user.name,
                role=c.role,
                accepted_at=c.accepted_at,
            ))

    return CollectionResponse(
        id=col.id,
        name=col.name,
        description=col.description,
        cover=col.cover,
        type=col.type,
        smart_rule=col.smart_rule,
        owner=OwnerResponse(id=owner.id, name=owner.name),
        recipes=recipes,
        collaborators=collabs,
        created_at=col.created_at,
        updated_at=col.updated_at,
    )


@router.post("", response_model=CollectionResponse, status_code=201)
def create_collection(
    body: CollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new manual collection."""
    col = Collection(
        owner_id=current_user.id,
        name=body.name,
        description=body.description,
        cover=body.cover,
        type="manual",
    )
    db.add(col)
    db.flush()

    # Add initial recipes
    for i, recipe_id in enumerate(body.recipe_ids):
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.owner_id == current_user.id).first()
        if recipe:
            db.add(CollectionRecipe(
                collection_id=col.id,
                recipe_id=recipe.id,
                sort_order=i,
                added_by=current_user.id,
            ))

    db.commit()
    db.refresh(col)
    return _build_collection_response(col, current_user.id, db)


@router.get("", response_model=CollectionListResponse)
def list_collections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all collections (owned + collaborated)."""
    # Owned collections
    owned = db.query(Collection).filter(Collection.owner_id == current_user.id).all()

    # Collaborated collections
    collab_ids = (
        db.query(Collaborator.collection_id)
        .filter(Collaborator.user_id == current_user.id, Collaborator.accepted_at.isnot(None))
        .all()
    )
    collab_collections = (
        db.query(Collection)
        .filter(Collection.id.in_([c[0] for c in collab_ids]))
        .all()
    ) if collab_ids else []

    items = []
    for col in owned + collab_collections:
        recipe_count = db.query(CollectionRecipe).filter(CollectionRecipe.collection_id == col.id).count()
        collab_count = db.query(Collaborator).filter(Collaborator.collection_id == col.id).count()
        items.append(CollectionListItem(
            id=col.id,
            name=col.name,
            cover=col.cover,
            type=col.type,
            smart_rule=col.smart_rule,
            recipe_count=recipe_count,
            is_owner=col.owner_id == current_user.id,
            collaborator_count=collab_count,
            updated_at=col.updated_at,
        ))

    return CollectionListResponse(collections=items)


@router.get("/smart/suggestions", response_model=SmartSuggestionsResponse)
def smart_suggestions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get auto-suggested smart collections based on the user's library."""
    # TODO: Analyze user's recipe library for patterns (cuisine clusters, tag frequencies, etc.)
    return SmartSuggestionsResponse(suggestions=[])


@router.post("/smart", response_model=CollectionResponse, status_code=201)
def create_smart_collection(
    body: SmartCollectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a smart collection with filter rules."""
    col = Collection(
        owner_id=current_user.id,
        name=body.name,
        type="smart",
        smart_rule=body.smart_rule,
    )
    db.add(col)
    db.commit()
    db.refresh(col)
    return _build_collection_response(col, current_user.id, db)


@router.get("/{collection_id}", response_model=CollectionResponse)
def get_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get collection detail with recipes and collaborators."""
    col = db.query(Collection).filter(Collection.id == collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    # Check access: owner or collaborator
    if col.owner_id != current_user.id:
        is_collab = db.query(Collaborator).filter(
            Collaborator.collection_id == collection_id,
            Collaborator.user_id == current_user.id,
        ).first()
        if not is_collab:
            raise HTTPException(status_code=403, detail="Access denied")
    return _build_collection_response(col, current_user.id, db)


@router.patch("/{collection_id}", response_model=CollectionResponse)
def update_collection(
    collection_id: str,
    body: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update collection metadata. Owner only."""
    col = db.query(Collection).filter(Collection.id == collection_id, Collection.owner_id == current_user.id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found or access denied")
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(col, field, value)
    db.commit()
    db.refresh(col)
    return _build_collection_response(col, current_user.id, db)


@router.delete("/{collection_id}", status_code=204)
def delete_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a collection. Does not delete recipes. Owner only."""
    col = db.query(Collection).filter(Collection.id == collection_id, Collection.owner_id == current_user.id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found or access denied")
    db.delete(col)
    db.commit()


@router.post("/{collection_id}/recipes", status_code=201)
def add_recipes_to_collection(
    collection_id: str,
    body: AddRecipesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add recipes to a collection."""
    col = db.query(Collection).filter(Collection.id == collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Get max sort_order
    max_order = (
        db.query(CollectionRecipe.sort_order)
        .filter(CollectionRecipe.collection_id == collection_id)
        .order_by(CollectionRecipe.sort_order.desc())
        .first()
    )
    next_order = (max_order[0] + 1) if max_order else 0

    for recipe_id in body.recipe_ids:
        # Check not already in collection
        existing = db.query(CollectionRecipe).filter(
            CollectionRecipe.collection_id == collection_id,
            CollectionRecipe.recipe_id == recipe_id,
        ).first()
        if not existing:
            db.add(CollectionRecipe(
                collection_id=collection_id,
                recipe_id=recipe_id,
                sort_order=next_order,
                added_by=current_user.id,
            ))
            next_order += 1

    db.commit()
    return {"status": "ok"}


@router.delete("/{collection_id}/recipes/{recipe_id}", status_code=204)
def remove_recipe_from_collection(
    collection_id: str,
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a recipe from a collection."""
    membership = db.query(CollectionRecipe).filter(
        CollectionRecipe.collection_id == collection_id,
        CollectionRecipe.recipe_id == recipe_id,
    ).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Recipe not in collection")
    db.delete(membership)
    db.commit()


@router.patch("/{collection_id}/reorder")
def reorder_recipes(
    collection_id: str,
    body: ReorderRecipesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update recipe display order within a collection."""
    for i, recipe_id in enumerate(body.recipe_order):
        membership = db.query(CollectionRecipe).filter(
            CollectionRecipe.collection_id == collection_id,
            CollectionRecipe.recipe_id == recipe_id,
        ).first()
        if membership:
            membership.sort_order = i
    db.commit()
    return {"status": "ok"}


# --- Sharing & Collaboration ---

@router.post("/{collection_id}/invite", response_model=InviteResponse, status_code=201)
def invite_collaborator(
    collection_id: str,
    body: InviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invite a user to collaborate on a collection. Owner only."""
    col = db.query(Collection).filter(Collection.id == collection_id, Collection.owner_id == current_user.id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found or access denied")

    # TODO: Generate real invite link, send email notification
    from datetime import datetime, timedelta
    import uuid

    invite_id = f"inv_{uuid.uuid4().hex[:12]}"
    return InviteResponse(
        invite_id=invite_id,
        collection_id=collection_id,
        invited_email=body.email,
        role=body.role,
        invite_link=f"https://recipeapp.com/invite/{invite_id}",
        expires_at=datetime.utcnow() + timedelta(days=7),
    )


@router.get("/{collection_id}/collaborators")
def list_collaborators(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List collaborators. Owner only."""
    col = db.query(Collection).filter(Collection.id == collection_id, Collection.owner_id == current_user.id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found or access denied")

    collabs = []
    for c in col.collaborators:
        user = db.query(User).filter(User.id == c.user_id).first()
        if user:
            collabs.append(CollaboratorResponse(
                user_id=user.id, name=user.name, role=c.role, accepted_at=c.accepted_at,
            ))
    return {"collaborators": collabs}


@router.patch("/{collection_id}/collaborators/{user_id}")
def update_collaborator_role(
    collection_id: str,
    user_id: str,
    body: UpdateRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change a collaborator's role. Owner only."""
    col = db.query(Collection).filter(Collection.id == collection_id, Collection.owner_id == current_user.id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found or access denied")
    collab = db.query(Collaborator).filter(
        Collaborator.collection_id == collection_id, Collaborator.user_id == user_id,
    ).first()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    collab.role = body.role
    db.commit()
    return {"status": "ok"}


@router.delete("/{collection_id}/collaborators/{user_id}", status_code=204)
def remove_collaborator(
    collection_id: str,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a collaborator. Owner only."""
    col = db.query(Collection).filter(Collection.id == collection_id, Collection.owner_id == current_user.id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found or access denied")
    collab = db.query(Collaborator).filter(
        Collaborator.collection_id == collection_id, Collaborator.user_id == user_id,
    ).first()
    if not collab:
        raise HTTPException(status_code=404, detail="Collaborator not found")
    db.delete(collab)
    db.commit()


@router.post("/{collection_id}/duplicate", response_model=DuplicateResponse, status_code=201)
def duplicate_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Duplicate a collection and all its recipes into the current user's library."""
    col = db.query(Collection).filter(Collection.id == collection_id).first()
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")

    # TODO: Deep copy all recipes and create new collection
    # For now, stub response
    return DuplicateResponse(new_collection_id="col_stub", recipes_duplicated=0)
