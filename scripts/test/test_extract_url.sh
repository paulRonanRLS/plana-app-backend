#!/usr/bin/env bash
#
# Test POST /v1/extract/url endpoint
#
# Usage: ./test_extract_url.sh [url]
#

set -e

# Get script directory and source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

# Use provided URL or default
URL="${1:-https://www.bbcgoodfood.com/recipes/one-pot-goulash-pasta}"

echo "🌐 Testing POST /v1/extract/url..."
echo ""
echo "URL: $URL"
echo ""
echo "Making request..."

# Create JSON payload
PAYLOAD=$(cat <<EOF
{
  "url": "${URL}"
}
EOF
)

# Make the request
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "${API_BASE_URL}/v1/extract/url")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Success (HTTP 200)"
  echo ""
  echo "$BODY" | python3 -m json.tool
  echo ""

  # Extract and display key metadata
  EXTRACTION_METHOD=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('extraction_metadata', {}).get('extraction_method', 'N/A'))" 2>/dev/null)
  CACHE_HIT=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('extraction_metadata', {}).get('cache_hit', 'N/A'))" 2>/dev/null)
  PROCESSING_TIME=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('extraction_metadata', {}).get('processing_time_ms', 'N/A'))" 2>/dev/null)
  TITLE=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', 'N/A'))" 2>/dev/null)
  ATTRIBUTION=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('source_attribution', 'N/A'))" 2>/dev/null)
  NUM_INGREDIENTS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('ingredients', [])))" 2>/dev/null)
  NUM_STEPS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('steps', [])))" 2>/dev/null)

  echo "📋 Summary:"
  echo "   Title: $TITLE"
  echo "   Attribution: $ATTRIBUTION"
  echo "   Extraction method: $EXTRACTION_METHOD"
  echo "   Cache hit: $CACHE_HIT"
  echo "   Processing time: ${PROCESSING_TIME}ms"
  echo "   Ingredients extracted: $NUM_INGREDIENTS"
  echo "   Steps extracted: $NUM_STEPS"
elif [ "$HTTP_CODE" = "500" ]; then
  echo "❌ Server Error (HTTP 500)"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  echo ""
  echo "💡 This might be due to:"
  echo "   - URL blocking the request (User-Agent, rate limiting)"
  echo "   - Claude API error"
  echo "   - Network timeout"
  exit 1
else
  echo "❌ Failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
