#!/usr/bin/env bash
#
# Test POST /v1/extract/photo endpoint
#
# Usage: ./test_extract_photo.sh /path/to/image.jpg
#

set -e

# Get script directory and source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

# Check if image path provided
if [ -z "$1" ]; then
  echo "❌ Error: No image file provided" >&2
  echo "" >&2
  echo "Usage: $0 /path/to/image.jpg" >&2
  exit 1
fi

IMAGE_PATH="$1"

# Check if file exists
if [ ! -f "$IMAGE_PATH" ]; then
  echo "❌ Error: File not found: $IMAGE_PATH" >&2
  exit 1
fi

# Check file extension
case "$IMAGE_PATH" in
  *.jpg|*.jpeg|*.JPG|*.JPEG|*.png|*.PNG)
    ;;
  *)
    echo "⚠️  Warning: File doesn't have .jpg or .png extension" >&2
    ;;
esac

echo "📸 Testing POST /v1/extract/photo..."
echo ""
echo "Image: $IMAGE_PATH"
echo ""
echo "Making request..."

# Make the request with multipart/form-data
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "image=@${IMAGE_PATH}" \
  "${API_BASE_URL}/v1/extract/photo")

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
  OCR_CONFIDENCE=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('extraction_metadata', {}).get('ocr_confidence', 'N/A'))" 2>/dev/null)
  TITLE=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', 'N/A'))" 2>/dev/null)
  NUM_INGREDIENTS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('ingredients', [])))" 2>/dev/null)
  NUM_STEPS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('steps', [])))" 2>/dev/null)

  echo "📋 Summary:"
  echo "   Title: $TITLE"
  echo "   Extraction method: $EXTRACTION_METHOD"
  echo "   OCR confidence: $OCR_CONFIDENCE"
  echo "   Processing time: ${PROCESSING_TIME}ms"
  echo "   Ingredients extracted: $NUM_INGREDIENTS"
  echo "   Steps extracted: $NUM_STEPS"

  if [ "$EXTRACTION_METHOD" = "ocr_pending" ]; then
    echo ""
    echo "ℹ️  Note: Photo extraction is currently stubbed (returns mock data)"
    echo "   Real OCR implementation coming in Session 2"
  fi
elif [ "$HTTP_CODE" = "400" ]; then
  echo "❌ Bad Request (HTTP 400)"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  echo ""
  echo "💡 This might be due to:"
  echo "   - Invalid image format (only JPEG and PNG supported)"
  echo "   - Image too large (>10MB)"
  exit 1
else
  echo "❌ Failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
