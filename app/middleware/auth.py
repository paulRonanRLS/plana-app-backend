from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.database import get_db
from app.models.user import User

# Test user for development (when Firebase is not configured)
DEV_USER = {
    "id": "usr_dev_000001",
    "name": "Dev User",
    "email": "dev@recipe.local",
    "avatar_url": None,
    "auth_provider": "google",
    "firebase_uid": "dev_firebase_uid",
    "preferred_units": "metric",
    "default_servings": 4,
    "voice_enabled": True,
}


def _ensure_dev_user(db: Session) -> User:
    """Create the dev user if it doesn't exist."""
    user = db.query(User).filter(User.id == DEV_USER["id"]).first()
    if not user:
        user = User(**DEV_USER)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Authenticate the current user.

    In development (no Firebase credentials configured): returns a test user.
    In production: verifies the Firebase ID token from the Authorization header.
    """

    # Dev mode bypass — no Firebase needed
    if not settings.firebase_credentials_path:
        return _ensure_dev_user(db)

    # Production: verify Firebase token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split("Bearer ")[1]

    try:
        # Lazy import — only needed when Firebase is configured
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            cred = firebase_admin.credentials.Certificate(settings.firebase_credentials_path)
            firebase_admin.initialize_app(cred)

        decoded = firebase_auth.verify_id_token(token)
        firebase_uid = decoded["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    # Look up user by Firebase UID
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found. Please log in first.")

    return user
