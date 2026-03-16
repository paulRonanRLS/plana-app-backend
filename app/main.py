import os
import toml
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.firebase import init_firebase
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.routers import auth, recipes, collections, extraction, users, cook_logs

# Read version from pyproject.toml
_project_root = Path(__file__).parent.parent
_pyproject_path = _project_root / "pyproject.toml"
_version = "0.1.0"  # default
try:
    pyproject_data = toml.load(_pyproject_path)
    _version = pyproject_data.get("tool", {}).get("poetry", {}).get("version", "0.1.0")
except Exception:
    pass  # Use default version if file can't be read


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # Initialize Firebase Admin SDK
    init_firebase()

    # Create local upload directory if not using GCS
    if not settings.use_gcs:
        os.makedirs("uploads", exist_ok=True)

    print(f"🍳 Recipe App API starting ({settings.app_env})")
    print(f"📄 Swagger UI: http://localhost:8000/docs")
    print(f"📄 ReDoc: http://localhost:8000/redoc")
    yield
    print("Recipe App API shutting down")


app = FastAPI(
    title="Recipe App API",
    description="Capture, Collect, Cook — Recipe management API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (local uploads when not using GCS)
if not settings.use_gcs:
    os.makedirs("uploads", exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Routes
app.include_router(auth.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(recipes.router, prefix="/v1")
app.include_router(collections.router, prefix="/v1")
app.include_router(cook_logs.router, prefix="/v1")
app.include_router(extraction.router, prefix="/v1")


@app.get("/health")
def health_check():
    """
    Basic health check endpoint for Railway and monitoring tools.

    Returns service status, version, and environment.
    No authentication required.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "version": _version,
        "environment": settings.app_env
    }


@app.get("/v1/config")
def get_config(current_user: User = Depends(get_current_user)):
    """
    Get full service configuration state.

    Requires authentication. Returns enabled/disabled state and
    non-sensitive config values. Never exposes API keys or credentials.
    """
    settings = get_settings()

    return {
        "environment": settings.app_env,
        "services": {
            "firebase": {
                "enabled": settings.firebase_enabled,
                "project_id": settings.firebase_project_id
            },
            "claude": {
                "enabled": settings.claude_enabled,
                "model": "claude-haiku-4-5-20251001"  # Current model in use
            },
            "google_cloud_vision": {
                "enabled": settings.google_cloud_enabled
            },
            "google_cloud_storage": {
                "enabled": settings.use_gcs,
                "bucket": settings.gcs_bucket_name if settings.use_gcs else None
            },
            "redis": {
                "enabled": settings.redis_enabled,
                "url": settings.redis_url if settings.redis_enabled else None
            }
        },
        "storage_backend": "gcs" if settings.use_gcs else "local",
        "extraction": {
            "caption_enabled": True,  # Always enabled
            "url_enabled": True,      # Always enabled
            "photo_enabled": True,    # Always enabled
            "cache_enabled": settings.redis_enabled  # Depends on Redis
        }
    }
