import logging
import os
import sys
import toml
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.core.firebase import init_firebase
from app.database import engine
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.routers import auth, recipes, collections, extraction, users, cook_logs, larder

logger = logging.getLogger(__name__)

# Read version from pyproject.toml
_project_root = Path(__file__).parent.parent
_pyproject_path = _project_root / "pyproject.toml"
_version = "0.1.0"  # default
try:
    pyproject_data = toml.load(_pyproject_path)
    _version = pyproject_data.get("tool", {}).get("poetry", {}).get("version", "0.1.0")
except Exception:
    pass  # Use default version if file can't be read


class StartupError(RuntimeError):
    """Raised when a critical dependency is unavailable at startup."""


def _check_database() -> None:
    """Verify database is reachable. Raises StartupError on failure."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Startup check: Database connected")
    except Exception as e:
        raise StartupError(f"Database unreachable: {e}") from e


def _check_redis() -> None:
    """Verify Redis is reachable if enabled. Logs warning if unavailable."""
    settings = get_settings()
    if not settings.redis_enabled:
        logger.info("Startup check: Redis disabled")
        return

    from app.core.redis_client import get_redis
    client = get_redis()
    if client is None:
        logger.warning(
            "Startup check: Redis enabled but unavailable — "
            "continuing without cache"
        )
        return

    logger.info("Startup check: Redis connected")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # Initialize Firebase Admin SDK
    init_firebase()

    # Critical startup checks — abort if a required service is missing
    try:
        _check_database()
    except StartupError as e:
        logger.critical(f"STARTUP ABORTED: {e}")
        sys.exit(1)

    # Non-critical checks — warn and continue
    _check_redis()

    # Create local upload directory if not using GCS
    if not settings.use_gcs:
        os.makedirs("uploads", exist_ok=True)

    print(f"Recipe App API starting ({settings.app_env})")
    print(f"  Swagger UI: http://localhost:8000/docs")
    print(f"  ReDoc: http://localhost:8000/redoc")
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
app.include_router(larder.router, prefix="/v1")


@app.get("/health")
def health_check():
    """
    Liveness probe — confirms the process is running.

    No authentication required. Does not check dependencies.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "version": _version,
        "environment": settings.app_env
    }


@app.get("/health/ready")
def readiness_check():
    """
    Readiness probe — confirms the service can handle requests.

    Checks database connectivity and optionally Redis.
    No authentication required.
    """
    settings = get_settings()
    checks: dict = {}
    healthy = True

    # Database (critical)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False
        logger.error(f"Readiness check: database unhealthy: {e}")

    # Redis (non-critical)
    if settings.redis_enabled:
        try:
            from app.core.redis_client import get_redis
            client = get_redis()
            if client and client.ping():
                checks["redis"] = "ok"
            else:
                checks["redis"] = "unavailable"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            logger.warning(f"Readiness check: redis unhealthy: {e}")
    else:
        checks["redis"] = "disabled"

    from fastapi.responses import JSONResponse
    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if healthy else "degraded",
            "version": _version,
            "checks": checks,
        }
    )


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
