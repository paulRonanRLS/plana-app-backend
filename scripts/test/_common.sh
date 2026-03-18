#!/usr/bin/env bash
#
# Common utilities for API test scripts
# Sources .env and gets Firebase authentication token
#

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Load .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
  export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Set defaults
API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

# Validate required environment variables
if [ -z "$FIREBASE_WEB_API_KEY" ]; then
  echo "❌ Error: FIREBASE_WEB_API_KEY environment variable not set" >&2
  echo "   Set it in .env or export it in your shell" >&2
  exit 1
fi

if [ -z "$FIREBASE_TEST_EMAIL" ]; then
  echo "❌ Error: FIREBASE_TEST_EMAIL environment variable not set" >&2
  echo "   Set it in .env or export it in your shell" >&2
  exit 1
fi

if [ -z "$FIREBASE_TEST_PASSWORD" ]; then
  echo "❌ Error: FIREBASE_TEST_PASSWORD environment variable not set" >&2
  echo "   Set it in .env or export it in your shell" >&2
  exit 1
fi

# Get Firebase token
echo "🔐 Getting Firebase token..." >&2

# Firebase REST API endpoint
FIREBASE_URL="https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=${FIREBASE_WEB_API_KEY}"

# Request payload
PAYLOAD=$(cat <<EOF
{
  "email": "${FIREBASE_TEST_EMAIL}",
  "password": "${FIREBASE_TEST_PASSWORD}",
  "returnSecureToken": true
}
EOF
)

# Make the request
RESPONSE=$(curl -s -X POST "$FIREBASE_URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD")

# Check for errors
if echo "$RESPONSE" | grep -q '"error"'; then
  ERROR_MSG=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['error']['message'])" 2>/dev/null || echo "Unknown error")
  echo "❌ Firebase authentication failed: $ERROR_MSG" >&2
  exit 1
fi

# Extract token
TOKEN=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['idToken'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Error: No idToken in response" >&2
  exit 1
fi

echo "✓ Token acquired" >&2
echo "" >&2

# Export for use in calling scripts
export TOKEN
export API_BASE_URL
