"""
Collection endpoints - manage collections and sharing.

This router is a thin orchestration layer that delegates business logic to the service layer.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.dependencies.db import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.collection import Collection, CollectionRecipe, Collaborator, CollectionInvite
from app.schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionResponse, CollectionListItem,
    CollectionListResponse, CollectionRecipeItem, CollaboratorResponse, OwnerResponse,
    AddRecipesRequest, ReorderRecipesRequest, SmartCollectionCreate,
    SmartSuggestionsResponse, InviteRequest, InviteResponse,
    AcceptInviteRequest, UpdateRoleRequest, DuplicateResponse,
)
from app.services import collection_service

router = APIRouter(prefix="/collections", tags=["collections"])


def _build_collection_response(col: Collection, current_user_id: str, db: Session) -> CollectionResponse:
    """Build full collection response with recipes and collaborators."""
    owner = db.query(User).filter(User.id == col.owner_id).first()

    # Get recipes from service
    recipes = collection_service.get_recipes(db, col, User(id=current_user_id))

    recipe_items = []
    for i, recipe in enumerate(recipes):
        # Get sort_order from membership for manual collections
        sort_order = i
        if col.type == "manual":
            membership = next((m for m in col.recipe_memberships if m.recipe_id == recipe.id), None)
            if membership:
                sort_order = membership.sort_order

        recipe_items.append(CollectionRecipeItem(
            id=recipe.id,
            title=recipe.title,
            cover_image_url=recipe.cover_image_url,
            cuisine=recipe.cuisine,
            total_time=recipe.total_time,
            sort_order=sort_order,
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
        recipes=recipe_items,
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
    data = body.model_dump()
    data["type"] = "manual"

    collection = collection_service.create(db, current_user, data)
    return _build_collection_response(collection, current_user.id, db)


@router.get("", response_model=CollectionListResponse)
def list_collections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all collections (owned + collaborated)."""
    collections = collection_service.list_for_user(db, current_user)

    items = []
    for col in collections:
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
    data = body.model_dump()
    data["type"] = "smart"

    collection = collection_service.create(db, current_user, data)
    return _build_collection_response(collection, current_user.id, db)


@router.get("/{collection_id}", response_model=CollectionResponse)
def get_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get collection detail with recipes and collaborators."""
    collection = collection_service.get_by_id(db, collection_id, current_user)
    return _build_collection_response(collection, current_user.id, db)


@router.patch("/{collection_id}", response_model=CollectionResponse)
def update_collection(
    collection_id: str,
    body: CollectionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update collection metadata. Owner only."""
    collection = collection_service.get_by_id(db, collection_id, current_user)
    update_data = body.model_dump(exclude_unset=True)
    updated = collection_service.update(db, collection, current_user, update_data)
    return _build_collection_response(updated, current_user.id, db)


@router.delete("/{collection_id}", status_code=204)
def delete_collection(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a collection. Does not delete recipes. Owner only."""
    collection = collection_service.get_by_id(db, collection_id, current_user)
    collection_service.delete(db, collection, current_user)


@router.post("/{collection_id}/recipes", status_code=201)
def add_recipes_to_collection(
    collection_id: str,
    body: AddRecipesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add recipes to a collection.

    If a recipe is not owned by the collection owner, it will be duplicated first.
    Owner or editor collaborator only.
    """
    collection = collection_service.get_by_id(db, collection_id, current_user)
    collection_service.add_recipes(db, collection, current_user, body.recipe_ids)
    return {"status": "ok"}


@router.delete("/{collection_id}/recipes/{recipe_id}", status_code=204)
def remove_recipe_from_collection(
    collection_id: str,
    recipe_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a recipe from a collection. Owner or editor collaborator only."""
    collection = collection_service.get_by_id(db, collection_id, current_user)
    collection_service.remove_recipe(db, collection, current_user, recipe_id)


@router.patch("/{collection_id}/reorder")
def reorder_recipes(
    collection_id: str,
    body: ReorderRecipesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update recipe display order within a collection. Owner or editor collaborator only."""
    collection = collection_service.get_by_id(db, collection_id, current_user)
    collection_service.reorder_recipes(db, collection, current_user, body.recipe_order)
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
    collection = collection_service.get_by_id(db, collection_id, current_user)

    # Check owner
    if collection.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can invite collaborators")

    # Create invite
    invite = CollectionInvite(
        collection_id=collection_id,
        role=body.role,
        invited_email=body.email,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    # TODO: Send email notification with invite link
    invite_link = f"https://recipeapp.com/invite/{invite.token}"

    return InviteResponse(
        invite_id=invite.id,
        collection_id=collection_id,
        invited_email=body.email,
        role=body.role,
        invite_link=invite_link,
        expires_at=invite.expires_at,
    )


@router.get("/{collection_id}/collaborators")
def list_collaborators(
    collection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List collaborators. Owner only."""
    collection = collection_service.get_by_id(db, collection_id, current_user)

    if collection.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can list collaborators")

    collabs = []
    for c in collection.collaborators:
        user = db.query(User).filter(User.id == c.user_id).first()
        if user:
            collabs.append(CollaboratorResponse(
                user_id=user.id,
                name=user.name,
                role=c.role,
                accepted_at=c.accepted_at,
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
    collection = collection_service.get_by_id(db, collection_id, current_user)

    if collection.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can update collaborators")

    collab = db.query(Collaborator).filter(
        Collaborator.collection_id == collection_id,
        Collaborator.user_id == user_id,
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
    collection = collection_service.get_by_id(db, collection_id, current_user)

    if collection.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can remove collaborators")

    collab = db.query(Collaborator).filter(
        Collaborator.collection_id == collection_id,
        Collaborator.user_id == user_id,
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
    """
    Duplicate a collection and all its recipes into the current user's library.

    All recipes will be duplicated to the current user's ownership.
    """
    collection = collection_service.get_by_id(db, collection_id, current_user)

    # Get all recipes in the collection
    recipes = collection_service.get_recipes(db, collection, current_user)

    # Create new collection
    new_collection_data = {
        "name": f"{collection.name} (Copy)",
        "description": collection.description,
        "cover": collection.cover,
        "type": "manual",
        "recipe_ids": [],
    }
    new_collection = collection_service.create(db, current_user, new_collection_data)

    # Add all recipes (they'll be duplicated if not owned by current user)
    recipe_ids = [r.id for r in recipes]
    collection_service.add_recipes(db, new_collection, current_user, recipe_ids)

    return DuplicateResponse(
        new_collection_id=new_collection.id,
        recipes_duplicated=len(recipe_ids),
    )
