# Test Scripts Quick Reference

## Setup (One-time)

1. **Add to `.env`** (in project root):
```bash
FIREBASE_WEB_API_KEY=AIzaSyBJ_OshTdifDchLireeDVhwCUXk7uCuDEA
FIREBASE_TEST_EMAIL=test@rls-recipe.dev
FIREBASE_TEST_PASSWORD=TestPassword123!
```

2. **Start the server**:
```bash
poetry run uvicorn app.main:app --reload
```

## Available Commands

### No Authentication Needed

```bash
# Check server is running
./scripts/test/test_health.sh
```

### Authenticated Endpoints

```bash
# Get current user info
./scripts/test/test_users.sh

# Extract recipe from Instagram-style caption
./scripts/test/test_extract_caption.sh

# Extract recipe from URL (default: BBC Good Food)
./scripts/test/test_extract_url.sh

# Extract from custom URL
./scripts/test/test_extract_url.sh "https://cooking.nytimes.com/recipes/1015819-pasta-carbonara"

# Extract recipe from photo
./scripts/test/test_extract_photo.sh /path/to/image.jpg

# Create a test recipe
./scripts/test/test_create_recipe.sh
```

## Common Workflows

### Quick smoke test
```bash
./scripts/test/test_health.sh && \
./scripts/test/test_users.sh && \
./scripts/test/test_extract_caption.sh
```

### Test multiple recipe sites
```bash
# BBC Good Food (has JSON-LD)
./scripts/test/test_extract_url.sh "https://www.bbcgoodfood.com/recipes/easy-pancakes"

# NYT Cooking (has JSON-LD)
./scripts/test/test_extract_url.sh "https://cooking.nytimes.com/recipes/1015819-pasta-carbonara"

# Serious Eats (may need scraping fallback)
./scripts/test/test_extract_url.sh "https://www.seriouseats.com/best-carbonara-recipe"
```

### Save responses for inspection
```bash
./scripts/test/test_extract_caption.sh > output.json
cat output.json | python3 -m json.tool
```

### Watch server logs while testing
```bash
# Terminal 1: Start server with debug logs
poetry run uvicorn app.main:app --reload --log-level debug

# Terminal 2: Run tests
./scripts/test/test_extract_caption.sh
```

## What Each Script Shows

### test_health.sh
- ✅ Server status
- Version number

### test_users.sh
- 🔐 Authenticated user
- Firebase UID
- Email, name, preferences

### test_extract_caption.sh
- 📝 Extracted recipe from text
- Title, ingredients, steps
- Extraction method: `llm_caption`
- Processing time (~5-10 seconds)

### test_extract_url.sh
- 🌐 Extracted recipe from website
- Extraction method: `json_ld` or `llm_scrape`
- Source attribution
- Cover image URL
- Cache status
- Processing time (~5-15 seconds)

### test_extract_photo.sh
- 📸 Extracted recipe from image
- Currently returns mock data
- Real OCR coming in Session 2

### test_create_recipe.sh
- 🍳 Creates a simple test recipe
- Returns recipe ID
- Shows full recipe object

## Exit Codes

- `0` = Success
- `1` = Failure (check error message)

## Troubleshooting

**"FIREBASE_WEB_API_KEY not set"**
- Add credentials to `.env`

**"Failed to connect"**
- Start the server first
- Check it's running on port 8000

**"Authentication failed"**
- Verify Firebase credentials in `.env`
- Check the test user exists in Firebase Console

**"Claude returned invalid JSON"**
- Server will show debug logs with raw response
- Check `ANTHROPIC_API_KEY` is set

## Tips

- All scripts auto-load `.env` from project root
- Firebase token is fetched fresh each time (no caching needed)
- JSON responses are pretty-printed automatically
- Key fields are extracted and shown in a summary
- Full response is always shown above the summary
