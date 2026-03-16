"""
Auth endpoints.

POST /auth/login — called after Firebase social login completes on the client.
Verifies the Firebase token, creates the user record on first login,
and returns the full profile. All subsequent authenticated requests go
through get_current_user in app/dependencies/auth.py which also handles
auto-creation, so this endpoint is mainly used to get the is_new_user flag
and bootstrap the client session.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.dependencies.db import get_db
from app.dependencies.auth import verify_firebase_token
from app.models.user import User
from app.schemas.user import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    Called after Firebase social login completes on the client.

    - Verifies the Firebase ID token to extract the real firebase_uid
    - Looks up the user by firebase_uid (consistent with get_current_user)
    - Creates user record on first login using token data + body fallbacks
    - Returns full profile plus is_new_user flag
    """
    # Verify token → get real firebase_uid and any data embedded in the token
    firebase_uid, token_data = verify_firebase_token(body.firebase_token, settings)

    # Look up by firebase_uid — same key used by get_current_user
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    is_new = user is None

    if is_new:
        # Prefer data extracted from the verified token; fall back to body fields
        user = User(
            firebase_uid=firebase_uid,
            name=token_data.get("name") or body.display_name,
            email=token_data.get("email") or body.email,
            avatar_url=token_data.get("picture") or body.avatar_url,
            auth_provider="google",
            preferred_units="metric",
            default_servings=4,
            voice_enabled=True,
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
