# API Test Scripts

Manual testing scripts for the Recipe App API endpoints. Each script handles Firebase authentication automatically and pretty-prints responses.

## Prerequisites

### 1. Environment Setup

Create a `.env` file in the project root with:

```bash
# Firebase credentials
FIREBASE_WEB_API_KEY=your_web_api_key_here
FIREBASE_TEST_EMAIL=test@example.com
FIREBASE_TEST_PASSWORD=YourTestPassword123

# Optional: API base URL (defaults to http://localhost:8000)
API_BASE_URL=http://localhost:8000
```

**Where to find Firebase Web API Key:**
1. Firebase Console → Project Settings → General
2. Scroll to "Your apps" section
3. Under "Web API Key", copy the value

**Test user:**
- Create a test user in Firebase Authentication (Email/Password provider)
- Use those credentials in your `.env` file

### 2. Running Server

Start the API server before running tests:

```bash
# With real Firebase and Claude
poetry run uvicorn app.main:app --reload

# Or stub mode (no credentials needed)
FIREBASE_ENABLED=false CLAUDE_ENABLED=false poetry run uvicorn app.main:app --reload
```

## Available Scripts

### Health Check (No Auth)

```bash
./scripts/test/test_health.sh
```

Tests that the server is running. No authentication required.

### User Info

```bash
./scripts/test/test_users.sh
```

Gets current user info from Firebase token. Shows:
- Firebase UID
- Email
- Display name

### Recipe Extraction - Caption

```bash
./scripts/test/test_extract_caption.sh
```

Tests caption extraction (e.g., Instagram post). Uses a hardcoded test caption with a simple carbonara recipe.

Shows:
- Extracted title
- Number of ingredients and steps
- Extraction method
- Processing time

### Recipe Extraction - URL

```bash
# Use default URL
./scripts/test/test_extract_url.sh

# Test with custom URL
./scripts/test/test_extract_url.sh "https://cooking.nytimes.com/recipes/1015819-pasta-carbonara"
```

Tests URL extraction with web scraping + JSON-LD parsing.

Shows:
- Extraction method (json_ld or llm_scrape)
- Cache hit status
- Processing time
- Attribution/author

**Good test URLs:**
- `https://www.bbcgoodfood.com/recipes/one-pot-goulash-pasta` (has JSON-LD)
- `https://cooking.nytimes.com/recipes/1015819-pasta-carbonara` (has JSON-LD)
- `https://www.seriouseats.com/best-carbonara-recipe` (may or may not have JSON-LD)

### Recipe Extraction - Photo

```bash
./scripts/test/test_extract_photo.sh /path/to/recipe-photo.jpg
```

Tests photo extraction (currently stubbed - returns mock data).

**Requirements:**
- JPEG or PNG format
- Under 10MB
- Must provide file path as argument

**Note:** Real OCR implementation coming in Session 2. Currently returns mock data with `extraction_method: "ocr_pending"`.

### Create Recipe

```bash
./scripts/test/test_create_recipe.sh
```

Creates a minimal test recipe (Quick Toast with Butter) and returns the created recipe ID.

## How It Works

### Authentication Flow

All scripts (except `test_health.sh`) use `_common.sh` which:

1. Loads `.env` file if present
2. Calls Firebase REST API to get an ID token
3. Exports `TOKEN` and `API_BASE_URL` for the test script
4. Shows `✓ Token acquired` when ready

### Response Formatting

All scripts:
- Show HTTP status code
- Pretty-print JSON responses using `python3 -m json.tool`
- Extract and display key fields in a summary section
- Exit with code 0 on success, 1 on failure

## Troubleshooting

### "FIREBASE_WEB_API_KEY environment variable not set"

Add the required variables to `.env` in the project root.

### "Firebase authentication failed"

- Check that `FIREBASE_TEST_EMAIL` and `FIREBASE_TEST_PASSWORD` match a valid user in Firebase Console
- Verify the Web API Key is correct

### "Failed to connect to server"

- Ensure the server is running on the expected port
- Check `API_BASE_URL` in `.env` or environment

### "Claude returned invalid JSON"

- Check server logs for debug output showing raw Claude response
- Ensure `ANTHROPIC_API_KEY` is set in `.env`
- Try with `CLAUDE_ENABLED=false` to use mock mode

## Examples

```bash
# Quick test of all endpoints
./scripts/test/test_health.sh
./scripts/test/test_users.sh
./scripts/test/test_extract_caption.sh
./scripts/test/test_create_recipe.sh

# Test URL extraction with different sites
./scripts/test/test_extract_url.sh "https://www.bbcgoodfood.com/recipes/easy-pancakes"
./scripts/test/test_extract_url.sh "https://cooking.nytimes.com/recipes/1022920-french-toast"

# Test photo extraction
./scripts/test/test_extract_photo.sh ~/Downloads/recipe-card.jpg
```

## Development Tips

### Watch server logs

When running extraction tests, watch the server output for:
- Debug logs showing raw Claude responses
- Processing times
- Error messages

```bash
# Run server with debug logging
poetry run uvicorn app.main:app --reload --log-level debug
```

### Chain tests

```bash
# Health check, then run extraction test
./scripts/test/test_health.sh && ./scripts/test/test_extract_caption.sh
```

### Save responses

```bash
# Save full JSON response to file
./scripts/test/test_extract_caption.sh > caption_response.json
```
