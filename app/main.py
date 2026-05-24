import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import tomllib
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import get_settings
from app.database import engine

logger = logging.getLogger(__name__)

_project_root = Path(__file__).parent.parent
_version = "0.1.0"
try:
    with open(_project_root / "pyproject.toml", "rb") as f:
        _version = tomllib.load(f).get("tool", {}).get("poetry", {}).get("version", "0.1.0")
except Exception:
    pass


class StartupError(RuntimeError):
    pass


def _check_database() -> None:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Startup check: Database connected")
    except Exception as e:
        raise StartupError(f"Database unreachable: {e}") from e


def _check_redis() -> None:
    settings = get_settings()
    if not settings.redis_enabled:
        logger.info("Startup check: Redis disabled")
        return

    from app.core.redis_client import get_redis
    client = get_redis()
    if client is None:
        logger.warning("Startup check: Redis enabled but unavailable — continuing without cache")
        return

    logger.info("Startup check: Redis connected")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    try:
        _check_database()
    except StartupError as e:
        logger.critical(f"STARTUP ABORTED: {e}")
        sys.exit(1)

    _check_redis()

    # ── Ingestion scheduler ────────────────────────────────────────────────────
    from app.ingestion.scheduler import create_scheduler
    scheduler = create_scheduler()
    scheduler.start()
    print("  Scheduler: garmin (06:00–09:00 ×1h + 10:00 backstop), strava (×30min), drift (08:30 daily), fade (Mon 09:00)")

    # ── Telegram bot ───────────────────────────────────────────────────────────
    bot_app = None
    if settings.telegram_enabled:
        if not settings.telegram_bot_token:
            logger.error("TELEGRAM_ENABLED=true but TELEGRAM_BOT_TOKEN not set — bot disabled")
        else:
            from app.bot.handler import create_application
            bot_app = create_application(settings.telegram_bot_token)
            await bot_app.initialize()
            await bot_app.start()
            await bot_app.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram bot polling started")
    else:
        logger.info("Telegram bot disabled (TELEGRAM_ENABLED=false)")

    print(f"planA API starting ({settings.app_env})")
    print(f"  Swagger UI: http://localhost:8000/docs")
    print(f"  ReDoc: http://localhost:8000/redoc")
    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    scheduler.shutdown(wait=False)
    logger.info("Ingestion scheduler stopped")

    if bot_app is not None:
        logger.info("Stopping Telegram bot...")
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()

    print("planA API shutting down")


app = FastAPI(
    title="planA API",
    description="Personal goal tracking — surface reality, acknowledge sacrifice, pursue what matters",
    version=_version,
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Web frontend static files
import os
os.makedirs("app/web", exist_ok=True)
app.mount("/web", StaticFiles(directory="app/web", html=True), name="web")


@app.get("/health")
def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "version": _version,
        "environment": settings.app_env,
    }


@app.get("/health/ready")
def readiness_check():
    from fastapi.responses import JSONResponse

    settings = get_settings()
    checks: dict = {}
    healthy = True

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False
        logger.error(f"Readiness check: database unhealthy: {e}")

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

    return JSONResponse(
        status_code=200 if healthy else 503,
        content={
            "status": "ok" if healthy else "degraded",
            "version": _version,
            "checks": checks,
        },
    )
