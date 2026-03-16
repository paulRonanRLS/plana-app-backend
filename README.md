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

The API supports two authentication modes:

**Stub Mode (Development/Testing):**
- Set `FIREBASE_ENABLED=false` in `.env` (default)
- Any Bearer token is accepted as a Firebase UID
- No Firebase credentials needed
- Perfect for frontend development and testing

**Real Firebase Mode (Production):**
- Set `FIREBASE_ENABLED=true` in `.env`
- Requires `FIREBASE_CREDENTIALS_PATH` pointing to service account JSON
- Verifies real Firebase ID tokens
- Auto-creates users from token data (email, name, avatar)

**Getting test tokens:**
```bash
# Set credentials in environment or .env
export FIREBASE_WEB_API_KEY="your-web-api-key"
export FIREBASE_TEST_EMAIL="test@example.com"
export FIREBASE_TEST_PASSWORD="password"

# Get a token
poetry run python scripts/get_firebase_token.py
```

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
├── core/                # Core infrastructure
│   ├── firebase.py      # Firebase Admin SDK initialization
│   └── storage.py       # File storage abstraction (local/S3)
├── dependencies/        # FastAPI dependencies
│   ├── auth.py          # Firebase token verification (stub/real modes)
│   └── db.py            # Database session dependency
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
├── routers/             # API endpoint handlers (thin layer)
│   ├── auth.py          # POST /auth/login, GET/PATCH /auth/me
│   ├── users.py         # GET/PATCH/DELETE /users/me
│   ├── recipes.py       # Full CRUD + notes
│   ├── collections.py   # CRUD + sharing + smart collections
│   ├── cook_logs.py     # Cook logs + voice notes
│   └── extraction.py    # Photo, URL, caption extraction (stubs)
└── services/            # Business logic layer
    ├── user_service.py
    ├── recipe_service.py
    ├── collection_service.py
    ├── cook_log_service.py
    ├── voice_note_service.py
    └── extraction_service.py
```

### Extraction Endpoints

The three extraction endpoints (`/v1/extract/photo`, `/v1/extract/url`, `/v1/extract/caption`) currently return mock data. They validate inputs and return the correct response shape so the frontend can be built against them. Real extraction logic will be added in the services layer.

### Testing

```bash
# Run all tests (uses SQLite in-memory, no Docker needed)
FIREBASE_ENABLED=false poetry run pytest

# Run with verbose output
FIREBASE_ENABLED=false poetry run pytest -v

# Run specific test file
poetry run pytest tests/unit/services/test_recipe_service.py -v

# Run tests matching a pattern
poetry run pytest -k "test_create" -v
```

**Important:** Always run tests with `FIREBASE_ENABLED=false`. Tests are designed to use stub authentication mode and don't require Firebase credentials.

### File Storage

Local development uses the `./uploads` directory, served at `/uploads`. The storage backend can be switched to S3 by setting `STORAGE_BACKEND=s3` and providing AWS credentials in `.env`.
