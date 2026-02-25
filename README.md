# Recipe App Backend

FastAPI backend for the Recipe App — Capture, Collect, Cook.

## Quick Start

### 1. Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL 16 and Redis 7. Verify with `docker ps`.

### 2. Install dependencies

```bash
poetry install
```

### 3. Set up environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for local development)
```

### 4. Run database migrations

```bash
poetry run alembic upgrade head
```

### 5. Start the server

```bash
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Explore the API

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health check**: http://localhost:8000/health

## Development Notes

### Authentication

In development (when `FIREBASE_CREDENTIALS_PATH` is not set in `.env`), the API automatically uses a test user — no Firebase setup needed. All authenticated endpoints work immediately.

### Database Migrations

```bash
# Create a new migration after changing models
poetry run alembic revision --autogenerate -m "description of changes"

# Apply migrations
poetry run alembic upgrade head

# Roll back one migration
poetry run alembic downgrade -1
```

### Project Structure

```
app/
├── main.py              # FastAPI app, middleware, route registration
├── config.py            # Pydantic settings (reads .env)
├── database.py          # SQLAlchemy engine, session, Base
├── models/              # SQLAlchemy ORM models (database tables)
│   ├── user.py
│   ├── recipe.py        # Recipe, Ingredient, Step, Equipment, Nutrition, Pairing
│   ├── collection.py    # Collection, CollectionRecipe, Collaborator
│   └── cook_log.py      # CookLog, VoiceNote
├── schemas/             # Pydantic schemas (request/response validation)
│   ├── user.py
│   ├── recipe.py        # Includes DraftRecipe for extraction responses
│   ├── collection.py
│   ├── cook_log.py
│   └── common.py        # Error schemas
├── routes/              # API endpoint handlers
│   ├── auth.py          # POST /auth/login, GET/PATCH /auth/me
│   ├── recipes.py       # Full CRUD + notes
│   ├── collections.py   # CRUD + sharing + smart collections
│   ├── cook_log.py      # Cook logs + voice notes
│   └── extraction.py    # Photo, URL, caption extraction (stubs)
├── services/            # Business logic (extraction pipeline, storage, cache)
└── middleware/
    └── auth.py          # Firebase token verification (dev bypass included)
```

### Extraction Endpoints

The three extraction endpoints (`/v1/extract/photo`, `/v1/extract/url`, `/v1/extract/caption`) currently return mock data. They validate inputs and return the correct response shape so the frontend can be built against them. Real extraction logic will be added in the services layer.

### File Storage

Local development uses the `./uploads` directory, served at `/uploads`. The storage backend can be switched to S3 by setting `STORAGE_BACKEND=s3` and providing AWS credentials in `.env`.
