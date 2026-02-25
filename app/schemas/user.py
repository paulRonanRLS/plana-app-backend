from pydantic import BaseModel
from datetime import datetime


class LoginRequest(BaseModel):
    firebase_token: str
    display_name: str
    email: str
    avatar_url: str | None = None


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    avatar_url: str | None
    auth_provider: str
    preferred_units: str
    default_servings: int
    voice_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class LoginResponse(UserResponse):
    is_new_user: bool


class UserUpdate(BaseModel):
    preferred_units: str | None = None
    default_servings: int | None = None
    voice_enabled: bool | None = None
    name: str | None = None
    avatar_url: str | None = None
