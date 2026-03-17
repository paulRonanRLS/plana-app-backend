# Recipe App — Backend

## Project Overview
FastAPI backend for a recipe management mobile app. Full design spec
is in docs/recipe-app-design-spec-v1.2.docx — read it for product 
context and API contract.

## Architecture
- **Pattern**: Thin routers → service layer → SQLAlchemy models
- **Routers**: app/routers/ (all routers live here)
- **Services**: app/services/ (all business logic lives here)
- **Models**: app/models/ (SQLAlchemy ORM)
- **Schemas**: app/schemas/ (Pydantic request/response)
- **Dependencies**: app/dependencies/ (auth, db session)
- **Core**: app/core/ (database, storage, firebase, security)

## Tech Stack
- Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic v2
- PostgreSQL (production), SQLite (tests)
- Redis (URL extraction cache with 30-day TTL)
- Poetry for dependency management

## Key Conventions
- All service methods take db as first argument after self
- Partial updates always use model_dump(exclude_unset=True)
- Ownership checks raise 403, missing resources raise 404
- External services (Firebase, GCS, Claude API, GCV) are behind
  abstractions with ENABLED flags for stub/real switching
- Never call external services directly from routers

## External Service Stubs
All external integrations have a stub mode controlled by env vars:
- **FIREBASE_ENABLED=false** → stub auth (any token accepted as UID)
  - Set to **true** for real Firebase authentication
  - Production: requires FIREBASE_CREDENTIALS_PATH and FIREBASE_PROJECT_ID
  - Tests: always run with stub mode (FIREBASE_ENABLED=false)
- **CLAUDE_ENABLED=false** → extraction service returns mock DraftRecipe
  - Set to **true** for real Claude API structuring
  - Production: requires ANTHROPIC_API_KEY
  - Tests: use stub mode (CLAUDE_ENABLED=false)
- **GOOGLE_CLOUD_ENABLED=false** → OCR returns mock text
  - Set to **true** for real Google Cloud Vision OCR
  - Production: requires GOOGLE_APPLICATION_CREDENTIALS
  - Tests: use stub mode (GOOGLE_CLOUD_ENABLED=false)
- **REDIS_ENABLED=false** → URL extraction caching disabled
  - Set to **true** for Redis caching (30-day TTL)
  - Production: requires Redis server at REDIS_URL
  - Tests: use stub mode (REDIS_ENABLED=false) for consistency
- **USE_GCS=false** → local filesystem storage
  - Set to **true** for Google Cloud Storage
  - Production: requires GCS_BUCKET_NAME and GOOGLE_APPLICATION_CREDENTIALS
  - Tests: use local storage (USE_GCS=false)

## Running the Project
```bash
# Start infrastructure
docker compose up -d

# Run server (with real Firebase - requires credentials file)
poetry run uvicorn app.main:app --reload

# Run server (stub mode - no Firebase credentials needed)
FIREBASE_ENABLED=false poetry run uvicorn app.main:app --reload

# Run tests (always use stub mode - no external services needed)
REDIS_ENABLED=false GOOGLE_CLOUD_ENABLED=false CLAUDE_ENABLED=false FIREBASE_ENABLED=false poetry run pytest

# Run specific test file
poetry run pytest tests/unit/services/test_recipe_service.py -v

# Database migrations
poetry run alembic upgrade head
poetry run alembic revision --autogenerate -m "description"
```

## Testing Firebase Authentication
```bash
# Get a test Firebase ID token (requires Firebase Web API key and test user)
export FIREBASE_WEB_API_KEY="AIzaSyBJ_OshTdifDchLireeDVhwCUXk7uCuDEA"
export FIREBASE_TEST_EMAIL="test@rls-recipe.dev"
export FIREBASE_TEST_PASSWORD="TestPassword123!"
poetry run python scripts/get_firebase_token.py

# Use token to test authenticated endpoints
TOKEN=$(poetry run python scripts/get_firebase_token.py 2>/dev/null)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/users/me

# Or use the provided test script
python test_firebase_auth.py $TOKEN
```

## Testing Approach

We have **three distinct levels** of testing:

### 1. Unit Tests (tests/unit/)
- **Purpose**: Test business logic in isolation
- **Execution**: Service methods directly, no HTTP layer
- **Database**: In-memory SQLite
- **External services**: All mocked
- **Speed**: < 1 second total
- **Count**: 58 tests

### 2. API Tests (tests/integration/api/)
- **Purpose**: Test HTTP endpoint contracts and request/response schemas
- **Execution**: Full HTTP layer via TestClient
- **Database**: In-memory SQLite
- **External services**: All return stub/mock data (CLAUDE_ENABLED=false, etc.)
- **Speed**: < 1 second total
- **Count**: 54 tests
- **Important**: These verify API contracts work but do NOT test real external integrations

### 3. Live Integration Tests (tests/integration/test_extraction_live.py)
- **Purpose**: Test actual external service integrations
- **Execution**: Full HTTP layer with real APIs
- **External services**: Claude API, Google Vision, Redis (Firebase still stubbed for fixtures)
- **Speed**: ~30 seconds (depends on API latency)
- **Count**: 5 tests (marked with @pytest.mark.live)
- **Requires**: Real API keys and running services
- **When to run**: Manually before deployments, not in CI

### Test Requirements
- All **112 non-live tests** must pass before any PR or session ends
- Live tests should pass before major deployments
- Never change test files to make tests pass — fix the implementation
- See tests/README.md for detailed testing philosophy

### Running Tests
```bash
# Run all non-live tests (default)
REDIS_ENABLED=false GOOGLE_CLOUD_ENABLED=false CLAUDE_ENABLED=false FIREBASE_ENABLED=false poetry run pytest -v -m "not live"

# Run only unit tests
poetry run pytest tests/unit/ -v

# Run only API tests
poetry run pytest tests/integration/api/ -v

# Run live integration tests (requires real services)
FIREBASE_ENABLED=false poetry run pytest -v -s -m live
```

## Startup Checks & Health Endpoints

### Startup Checks (app/main.py lifespan)
On boot the server verifies critical dependencies before accepting traffic:
- **Database** (`SELECT 1`) — **critical**: app will not start if the DB is unreachable
- **Redis** (ping) — **non-critical**: logs a warning and continues without cache
- **Firebase** — validated during `init_firebase()` (checks credentials file exists)

### Health Endpoints
- **`GET /health`** — Liveness probe. Confirms the process is running. Returns version and environment. Does **not** check dependencies. Always returns `200`.
- **`GET /health/ready`** — Readiness probe. Actively checks database connectivity (and Redis if enabled). Returns `200` with `"status": "ok"` when all critical deps are healthy, or `503` with `"status": "degraded"` and per-check details when the database is down. Use this for load balancer health checks and orchestrator readiness gates.
- **`GET /v1/config`** — Authenticated. Returns enabled/disabled state of all services. Not a health check — use for debugging service configuration.

## Current State
Business logic complete across all domains. External service
integrations status:
- ✅ Storage abstraction (LocalStorage working, GCSStorage implemented)
- ✅ Firebase auth (real verification implemented, stub mode for tests)
- ✅ Extraction service (Claude API, Google Cloud Vision, Trafilatura)
  - Caption extraction (Instagram-style text → structured recipe)
  - URL extraction (JSON-LD + scraping fallback → structured recipe)
  - Photo extraction (OCR + Claude → structured recipe)
- ✅ Redis URL caching (30-day TTL, graceful degradation on failure)

## Firebase Authentication Details
- **Implementation**: app/core/firebase.py, app/dependencies/auth.py
- **Mode switching**: FIREBASE_ENABLED env var
- **Token script**: scripts/get_firebase_token.py (dev tool for getting test tokens)
- **Features**:
  - Real Firebase ID token verification when enabled
  - Auto-creates users on first login with data from token (email, name, avatar)
  - Syncs token data to existing users (fills empty fields only)
  - Stub mode accepts any token as Firebase UID (for tests)

## Extraction Service Details
- **Implementation**: app/services/extraction_service.py, app/core/claude_client.py, app/core/vision_client.py, app/core/scraper.py
- **Mode switching**: CLAUDE_ENABLED, GOOGLE_CLOUD_ENABLED, REDIS_ENABLED env vars
- **Test scripts**: scripts/test/test_extract_caption.sh, test_extract_url.sh, test_extract_photo.sh
- **Features**:
  - Caption extraction: Instagram captions → structured DraftRecipe via Claude
  - URL extraction: JSON-LD parsing → structured data, fallback to Trafilatura scraping + Claude
  - Photo extraction: Google Cloud Vision OCR → text → Claude structuring
  - Redis caching: 30-day TTL on URL extractions, SHA256-based cache keys
  - Graceful degradation: All external services continue working when Redis/Vision/Claude fail
  - Stub mode: Returns mock DraftRecipe for testing without API keys

## Important Notes
- **Firebase credentials path**: The .env uses a relative path from recipe-app-backend/
  - Current: `../../secrets/rls-recipe-firebase-adminsdk-fbsvc-af8107b933.json`
  - This goes up two levels to /Users/paulronan/dev/secrets/
- **Running tests**: ALWAYS use `FIREBASE_ENABLED=false poetry run pytest`
  - Tests are designed for stub mode and don't need Firebase credentials
  - Running without the flag will fail if credentials aren't found

## Do Not
- Add new routers to app/routes/ — that directory was removed
- Use datetime.utcnow() — use datetime.now(timezone.utc) instead
- Hardcode any API keys or credentials
- Skip tests — always run the full suite after changes
- Run tests with FIREBASE_ENABLED=true — tests require stub mode
```

