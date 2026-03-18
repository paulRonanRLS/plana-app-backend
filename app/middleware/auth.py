import json
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import get_settings, Settings
from app.database import get_db
from app.models.user import User

# Test user for development (when Firebase is disabled)
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


def _init_firebase(settings: Settings) -> None:
    """
    Initialise Firebase Admin SDK from JSON string env var (idempotent).
    Uses firebase_credentials_json (a string containing the full service account JSON)
    rather than a file path — required for Railway's ephemeral filesystem.
    """
    import firebase_admin
    from firebase_admin import credentials

    if not firebase_admin._apps:
        cred_dict = json.loads(settings.firebase_credentials_json)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)


async def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """
    Authenticate the current user.

    In development (firebase_enabled=False): returns a hardcoded test user.
    In production (firebase_enabled=True): verifies the Firebase ID token from
    the Authorization header and upserts the user record on first login.
    """

    # Dev bypass — keyed off explicit flag, not the presence of a file path
    if not settings.firebase_enabled:
        return _ensure_dev_user(db)

    # Production: verify Firebase token
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split("Bearer ")[1]

    try:
        from firebase_admin import auth as firebase_auth
        _init_firebase(settings)
        decoded = firebase_auth.verify_id_token(token)
        firebase_uid = decoded["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Firebase token")

    # Upsert — create on first authenticated request if not yet in DB.
    # This covers any request that arrives before /auth/login is explicitly called.
    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()
    if not user:
        user = User(
            firebase_uid=firebase_uid,
            name=decoded.get("name"),
            email=decoded.get("email"),
            avatar_url=decoded.get("picture"),
            auth_provider="google",
            preferred_units="metric",
            default_servings=4,
            voice_enabled=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
