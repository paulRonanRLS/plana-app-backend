from pydantic import BaseModel
from datetime import datetime


class CollectionCreate(BaseModel):
    name: str
    description: str | None = None
    cover: str | None = None
    recipe_ids: list[str] = []


class CollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    cover: str | None = None


class CollectionListItem(BaseModel):
    id: str
    name: str
    cover: str | None
    type: str
    smart_rule: dict | None = None
    recipe_count: int = 0
    is_owner: bool = True
    collaborator_count: int = 0
    updated_at: datetime

    model_config = {"from_attributes": True}


class CollectionRecipeItem(BaseModel):
    id: str
    title: str
    cover_image_url: str | None
    cuisine: str | None
    total_time: int | None
    sort_order: int


class CollaboratorResponse(BaseModel):
    user_id: str
    name: str
    role: str
    accepted_at: datetime | None


class OwnerResponse(BaseModel):
    id: str
    name: str


class CollectionResponse(BaseModel):
    id: str
    name: str
    description: str | None
    cover: str | None
    type: str
    smart_rule: dict | None = None
    owner: OwnerResponse
    recipes: list[CollectionRecipeItem]
    collaborators: list[CollaboratorResponse]
    created_at: datetime
    updated_at: datetime


class CollectionListResponse(BaseModel):
    collections: list[CollectionListItem]


class AddRecipesRequest(BaseModel):
    recipe_ids: list[str]


class ReorderRecipesRequest(BaseModel):
    recipe_order: list[str]


class SmartCollectionCreate(BaseModel):
    name: str
    smart_rule: dict


class SmartSuggestion(BaseModel):
    name: str
    smart_rule: dict
    matching_count: int
    sample_recipes: list[str]


class SmartSuggestionsResponse(BaseModel):
    suggestions: list[SmartSuggestion]


class InviteRequest(BaseModel):
    email: str
    role: str = "editor"


class InviteResponse(BaseModel):
    invite_id: str
    collection_id: str
    invited_email: str
    role: str
    invite_link: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    invite_token: str


class UpdateRoleRequest(BaseModel):
    role: str


class DuplicateResponse(BaseModel):
    new_collection_id: str
    recipes_duplicated: int
