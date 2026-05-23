# planA — Backend

Personal goal tracking API. Surfaces reality, acknowledges sacrifice, pursues what matters.

## Quick Start

```bash
# Start infrastructure (TimescaleDB + Redis)
docker compose up -d

# Install dependencies
poetry install

# Run database migrations
poetry run alembic upgrade head

# Run server in stub mode (no external credentials needed)
CLAUDE_ENABLED=false TELEGRAM_ENABLED=false GARMIN_ENABLED=false STRAVA_ENABLED=false REDIS_ENABLED=false poetry run uvicorn app.main:app --reload

# Run tests
CLAUDE_ENABLED=false TELEGRAM_ENABLED=false GARMIN_ENABLED=false STRAVA_ENABLED=false REDIS_ENABLED=false poetry run pytest -v -m "not live"
```

## Configuration

Copy `.env.example` to `.env` and set credentials for whichever services you want to enable.
All external services default to stub mode — the server starts cleanly without any credentials.

- **CLAUDE_ENABLED** — real Claude API calls (requires ANTHROPIC_API_KEY)
- **TELEGRAM_ENABLED** — live Telegram bot (requires TELEGRAM_BOT_TOKEN)
- **GARMIN_ENABLED** — real Garmin Connect sync (requires GARMIN_EMAIL, GARMIN_PASSWORD)
- **STRAVA_ENABLED** — real Strava API (requires STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN)
- **REDIS_ENABLED** — session memory and caching (requires Redis at REDIS_URL)

## Architecture

```
app/
├── main.py              # FastAPI app, lifespan, health endpoints
├── config.py            # Settings (pydantic-settings, env-driven)
├── database.py          # SQLAlchemy engine, Base, session factory
├── core/
│   ├── claude_client.py # Anthropic API wrapper
│   └── redis_client.py  # Redis wrapper
├── models/              # SQLAlchemy ORM models (to be built)
├── schemas/             # Pydantic request/response schemas (to be built)
├── services/            # Business logic (to be built)
├── routers/             # FastAPI route handlers (to be built)
├── bot/                 # Telegram bot handler (to be built)
├── ingestion/           # Garmin + Strava sync jobs (to be built)
├── intelligence/        # LLM intent, milestones, memoir (to be built)
└── web/                 # Static HTML/JS frontend (to be built)
```

See `CLAUDE.md` for full architecture, conventions, and build order.

## Endpoints

- `GET /health` — liveness probe
- `GET /health/ready` — readiness probe (checks DB + Redis)
- `GET /docs` — Swagger UI
