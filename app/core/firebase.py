"""
Firebase Admin SDK initialization.

Initializes the Firebase Admin SDK for server-side authentication.
Guards against double-initialization and supports stub mode for testing.
"""

import json
import firebase_admin
from firebase_admin import credentials

from app.config import get_settings


def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK.

    Reads FIREBASE_CREDENTIALS_JSON from environment (full service account JSON
    as a string) and initializes the Firebase app with service account credentials.
    This approach is required for Railway, which has no persistent filesystem for secrets.

    Guards:
    - If FIREBASE_ENABLED=false, skip initialization (stub mode for testing)
    - If already initialized, skip (prevents double-initialization)
    - If credentials JSON not set, raise error

    Raises:
        ValueError: If Firebase is enabled but FIREBASE_CREDENTIALS_JSON is not set
        json.JSONDecodeError: If FIREBASE_CREDENTIALS_JSON is not valid JSON
    """
    settings = get_settings()

    # Skip initialization if Firebase is disabled (stub mode for tests)
    if not settings.firebase_enabled:
        print("🔥 Firebase: Disabled (stub mode)")
        return

    # Check if already initialized
    if firebase_admin._apps:
        print("🔥 Firebase: Already initialized")
        return

    # Validate credentials JSON string
    if not settings.firebase_credentials_json:
        raise ValueError(
            "FIREBASE_ENABLED=true but FIREBASE_CREDENTIALS_JSON not set. "
            "Set FIREBASE_CREDENTIALS_JSON to the full contents of your Firebase "
            "service account JSON file as a string."
        )

    # Initialize Firebase Admin SDK from JSON string (no file required)
    cred_dict = json.loads(settings.firebase_credentials_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred, {
        'projectId': settings.firebase_project_id,
    })

    print(f"🔥 Firebase: Initialized (project: {settings.firebase_project_id})")
