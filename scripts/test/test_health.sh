#!/usr/bin/env bash
#
# Test health endpoint (no auth required)
#

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Load .env for API_BASE_URL
if [ -f "$PROJECT_ROOT/.env" ]; then
  export $(grep -v '^#' "$PROJECT_ROOT/.env" | grep API_BASE_URL | xargs)
fi

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "🏥 Testing health endpoint..."
echo ""

# Try /health first, then /v1/health
RESPONSE=$(curl -s -w "\n%{http_code}" "${API_BASE_URL}/health" 2>/dev/null || echo "000")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "404" ]; then
  # Try /v1/health instead
  RESPONSE=$(curl -s -w "\n%{http_code}" "${API_BASE_URL}/v1/health" 2>/dev/null || echo "000")
  HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
  BODY=$(echo "$RESPONSE" | sed '$d')
fi

if [ "$HTTP_CODE" = "000" ]; then
  echo "❌ Failed to connect to server at ${API_BASE_URL}"
  echo "   Is the server running?"
  exit 1
elif [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Server is running at ${API_BASE_URL}"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 0
else
  echo "⚠️  Unexpected response (HTTP ${HTTP_CODE}):"
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
