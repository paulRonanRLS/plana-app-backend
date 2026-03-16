"""
Authentication dependency for FastAPI endpoints.

Verifies Firebase ID tokens and auto-creates users on first login.
Supports stub mode for testing when FIREBASE_ENABLED=false.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.dependencies.db import get_db
from app.models.user import User


def verify_firebase_token(token: str, settings: Settings) -> tuple[str, dict]:
    """
    Verify Firebase ID token and extract user information.

    Args:
        token: The Firebase ID token from Authorization header
        settings: Application settings

    Returns:
        Tuple of (firebase_uid, user_data) where user_data contains:
        - email: str | None
        - name: str | None
        - picture: str | None

    Raises:
        HTTPException: 401 if token is invalid or expired
    """
    # Stub mode: Accept any token as UID (for tests)
    if not settings.firebase_enabled:
        return token, {"email": None, "name": None, "picture": None}

    # Real Firebase verification
    try:
        from firebase_admin import auth as firebase_auth

        # Verify the ID token
        decoded_token = firebase_auth.verify_id_token(token)

        # Extract user info
        firebase_uid = decoded_token["uid"]
        user_data = {
            "email": decoded_token.get("email"),
            "name": decoded_token.get("name"),
            "picture": decoded_token.get("picture"),
        }

        return firebase_uid, user_data

    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Invalid or expired Firebase token: {str(e)}"
        )


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Authenticate the current user via Firebase ID token.

    Auto-creates user record on first login.

    Behavior:
    - FIREBASE_ENABLED=false (stub mode for tests):
      * Accepts any token as the Firebase UID
      * Creates/retrieves user with minimal info

    - FIREBASE_ENABLED=true (production):
      * Verifies the Firebase ID token
      * Extracts user info from the token (email, name, picture)
      * Auto-creates user on first login with token data
      * Syncs token data to existing users (fills gaps, respects edits)

    Returns:
        User: The authenticated user object

    Raises:
        HTTPException: 401 if no auth header or invalid token
    """

    # Extract token from Authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header"
        )

    token = auth_header.split("Bearer ")[1]

    # Verify token and extract user data
    firebase_uid, user_data = verify_firebase_token(token, settings)

    # Look up user by Firebase UID
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()

    # Auto-create user on first login
    if not user:
        if settings.firebase_enabled:
            # Production: Use extracted info from Firebase token
            user = User(
                firebase_uid=firebase_uid,
                name=user_data.get("name") or user_data.get("email", "").split("@")[0] or f"User {firebase_uid[:8]}",
                email=user_data.get("email") or f"{firebase_uid[:8]}@example.com",
                auth_provider="google",  # Default, can be enhanced later
                avatar_url=user_data.get("picture"),
                preferred_units="metric",
                default_servings=4,
                voice_enabled=True,
            )
        else:
            # Stub mode: Create with minimal info (for tests)
            user = User(
                firebase_uid=firebase_uid,
                name=f"User {firebase_uid[:8]}",
                email=f"{firebase_uid[:8]}@example.com",
                auth_provider="google",
                avatar_url=None,
                preferred_units="metric",
                default_servings=4,
                voice_enabled=True,
            )

        db.add(user)
        db.commit()
        db.refresh(user)

    else:
        # Existing user: Sync data from token if enabled
        # Only fill gaps (don't overwrite user edits)
        if settings.firebase_enabled:
            updated = False

            if not user.email and user_data.get("email"):
                user.email = user_data["email"]
                updated = True

            if not user.name and user_data.get("name"):
                user.name = user_data["name"]
                updated = True

            if not user.avatar_url and user_data.get("picture"):
                user.avatar_url = user_data["picture"]
                updated = True

            if updated:
                db.commit()
                db.refresh(user)

    return user
