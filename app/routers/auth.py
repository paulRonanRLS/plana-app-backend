from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse, UserResponse, UserUpdate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Called after Firebase social login completes on the client.
    Creates user record on first login, returns profile on subsequent logins.
    """
    # Check if user already exists by email
    user = db.query(User).filter(User.email == body.email).first()
    is_new = user is None

    if is_new:
        user = User(
            name=body.display_name,
            email=body.email,
            avatar_url=body.avatar_url,
            auth_provider="google",  # TODO: detect from Firebase token
            firebase_uid=body.firebase_token[:128],  # Placeholder — use real UID in production
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return LoginResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        auth_provider=user.auth_provider,
        preferred_units=user.preferred_units,
        default_servings=user.default_servings,
        voice_enabled=user.voice_enabled,
        created_at=user.created_at,
        is_new_user=is_new,
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user profile."""
    return current_user


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user preferences."""
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)
    return current_user
