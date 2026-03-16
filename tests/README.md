# Test Structure

This project has three distinct levels of testing with different purposes and requirements.

## 1. Unit Tests (`tests/unit/`)

**Purpose**: Test individual functions and business logic in isolation

**Characteristics**:
- Tests service methods directly (no HTTP layer)
- Uses in-memory SQLite database
- All external dependencies are mocked
- Fast execution (< 1 second total)
- No API keys or external services required

**Run command**:
```bash
REDIS_ENABLED=false GOOGLE_CLOUD_ENABLED=false CLAUDE_ENABLED=false FIREBASE_ENABLED=false poetry run pytest tests/unit/ -v
```

**What they verify**:
- Service layer business logic is correct
- Database operations work correctly
- Error handling and validation logic
- Edge cases and boundary conditions

## 2. API Tests (`tests/integration/api/`)

**Purpose**: Test HTTP API endpoints and request/response contracts

**Characteristics**:
- Tests via FastAPI TestClient (full HTTP layer)
- Uses in-memory SQLite database
- All external services return stub/mock data
- Fast execution (< 1 second total)
- No API keys or external services required

**Run command**:
```bash
REDIS_ENABLED=false GOOGLE_CLOUD_ENABLED=false CLAUDE_ENABLED=false FIREBASE_ENABLED=false poetry run pytest tests/integration/api/ -v
```

**What they verify**:
- HTTP endpoints return correct status codes
- Request/response schemas are valid
- Authentication/authorization logic
- Error responses have correct format
- **NOT testing actual external API integrations**

**Important**: These are often called "integration tests" but they're really **API contract tests** since external services are stubbed. They verify the API surface works correctly in isolation.

## 3. Live Integration Tests (`tests/integration/test_extraction_live.py`)

**Purpose**: Test actual integrations with real external services

**Characteristics**:
- Tests via FastAPI TestClient (HTTP layer)
- Calls real external APIs (Claude, Google Vision, Redis)
- Firebase auth still stubbed (for test fixtures to work)
- Slow execution (~30 seconds total, depends on API latency)
- **Requires real API keys and running services**
- Marked with `@pytest.mark.live`

**Run command**:
```bash
# Requires: ANTHROPIC_API_KEY, GOOGLE_APPLICATION_CREDENTIALS, Redis running
FIREBASE_ENABLED=false poetry run pytest -v -s -m live
```

**What they verify**:
- Claude API integration works (caption/URL/photo extraction)
- Google Cloud Vision OCR works (text extraction from images)
- Redis caching works (cache hit/miss behavior)
- Real-world error handling (API timeouts, rate limits, etc.)

**When to run**: Manually before major deployments, not in CI

---

## Test Count Summary

- **Unit tests**: 58 tests
- **API tests**: 54 tests
- **Live integration tests**: 5 tests (4 pass, 1 skipped if no test image)

**Total**: 112 non-live tests must always pass before any PR or deployment

## Running All Tests

```bash
# Run all non-live tests (unit + API)
REDIS_ENABLED=false GOOGLE_CLOUD_ENABLED=false CLAUDE_ENABLED=false FIREBASE_ENABLED=false poetry run pytest -v -m "not live"

# Run only live tests (manual, requires real services)
FIREBASE_ENABLED=false poetry run pytest -v -s -m live

# Run everything
FIREBASE_ENABLED=false poetry run pytest -v -s
```

## Why Stub External Services in Most Tests?

1. **Speed**: Stubbed tests run in < 1 second vs 30+ seconds with real APIs
2. **Reliability**: Tests don't fail due to network issues or API downtime
3. **Cost**: Avoid consuming API quota during development
4. **Consistency**: Same results every time, no rate limits or timeouts
5. **CI/CD**: Can run on any machine without credentials

The trade-off is that we need live tests to verify real integrations work, but those are run manually, not on every commit.
