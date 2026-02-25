import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes import auth, recipes, collections, cook_log, extraction


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # Create local upload directory if using local storage
    if settings.storage_backend == "local":
        os.makedirs(settings.local_upload_dir, exist_ok=True)

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

# Static files (local uploads in development)
if settings.storage_backend == "local":
    os.makedirs(settings.local_upload_dir, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.local_upload_dir), name="uploads")

# Routes
app.include_router(auth.router, prefix="/v1")
app.include_router(recipes.router, prefix="/v1")
app.include_router(collections.router, prefix="/v1")
app.include_router(cook_log.router, prefix="/v1")
app.include_router(extraction.router, prefix="/v1")


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0"}
