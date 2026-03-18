#!/usr/bin/env bash
#
# Test GET /v1/users/me endpoint
#

set -e

# Get script directory and source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

echo "👤 Testing GET /v1/users/me..."
echo ""

# Make the request
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${API_BASE_URL}/v1/users/me")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Success (HTTP 200)"
  echo ""
  echo "$BODY" | python3 -m json.tool
  echo ""

  # Extract and display key fields
  FIREBASE_UID=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('firebase_uid', 'N/A'))" 2>/dev/null)
  EMAIL=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('email', 'N/A'))" 2>/dev/null)
  NAME=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('name', 'N/A'))" 2>/dev/null)

  echo "📋 Summary:"
  echo "   Firebase UID: $FIREBASE_UID"
  echo "   Email: $EMAIL"
  echo "   Name: $NAME"
else
  echo "❌ Failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
