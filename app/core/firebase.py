"""
Firebase Admin SDK initialization.

Initializes the Firebase Admin SDK for server-side authentication.
Guards against double-initialization and supports stub mode for testing.
"""

import os
import firebase_admin
from firebase_admin import credentials

from app.config import get_settings


def init_firebase() -> None:
    """
    Initialize Firebase Admin SDK.

    Reads FIREBASE_CREDENTIALS_PATH from environment and initializes
    the Firebase app with service account credentials.

    Guards:
    - If FIREBASE_ENABLED=false, skip initialization (stub mode for testing)
    - If already initialized, skip (prevents double-initialization)
    - If credentials path doesn't exist, raise error

    Raises:
        FileNotFoundError: If credentials file doesn't exist when Firebase is enabled
        ValueError: If Firebase is enabled but credentials path not set
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

    # Validate credentials path
    if not settings.firebase_credentials_path:
        raise ValueError(
            "FIREBASE_ENABLED=true but FIREBASE_CREDENTIALS_PATH not set. "
            "Set FIREBASE_CREDENTIALS_PATH to the path of your Firebase service account JSON file."
        )

    if not os.path.exists(settings.firebase_credentials_path):
        raise FileNotFoundError(
            f"Firebase credentials file not found: {settings.firebase_credentials_path}"
        )

    # Initialize Firebase Admin SDK
    cred = credentials.Certificate(settings.firebase_credentials_path)
    firebase_admin.initialize_app(cred, {
        'projectId': settings.firebase_project_id,
    })

    print(f"🔥 Firebase: Initialized (project: {settings.firebase_project_id})")
