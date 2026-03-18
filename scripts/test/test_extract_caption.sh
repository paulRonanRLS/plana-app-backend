#!/usr/bin/env bash
#
# Test POST /v1/extract/caption endpoint
#

set -e

# Get script directory and source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

echo "📝 Testing POST /v1/extract/caption..."
echo ""

# Test caption
CAPTION="Classic Spaghetti Carbonara. You will need: 400g spaghetti, 200g guanciale, 4 egg yolks, 100g pecorino romano, black pepper. Start by boiling a large pot of salted water. Cook the spaghetti for 10 minutes until al dente. Meanwhile fry the guanciale in a pan for 5 minutes until crispy. Remove from heat. Mix egg yolks with pecorino in a bowl. Add pasta to guanciale pan off the heat, add egg mixture and toss quickly adding pasta water to loosen. Season with black pepper. Serves 4."

# Create JSON payload
PAYLOAD=$(cat <<EOF
{
  "caption_text": "${CAPTION}",
  "source_url": "https://instagram.com/p/test123"
}
EOF
)

echo "Caption: ${CAPTION:0:80}..."
echo ""
echo "Making request..."

# Make the request
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "${API_BASE_URL}/v1/extract/caption")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Success (HTTP 200)"
  echo ""
  echo "$BODY" | python3 -m json.tool
  echo ""

  # Extract and display key metadata
  EXTRACTION_METHOD=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('extraction_metadata', {}).get('extraction_method', 'N/A'))" 2>/dev/null)
  PROCESSING_TIME=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('extraction_metadata', {}).get('processing_time_ms', 'N/A'))" 2>/dev/null)
  TITLE=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', 'N/A'))" 2>/dev/null)
  NUM_INGREDIENTS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('ingredients', [])))" 2>/dev/null)
  NUM_STEPS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('steps', [])))" 2>/dev/null)

  echo "📋 Summary:"
  echo "   Title: $TITLE"
  echo "   Extraction method: $EXTRACTION_METHOD"
  echo "   Processing time: ${PROCESSING_TIME}ms"
  echo "   Ingredients extracted: $NUM_INGREDIENTS"
  echo "   Steps extracted: $NUM_STEPS"
else
  echo "❌ Failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
