#!/usr/bin/env bash
#
# Test GET /v1/config endpoint
#

set -e

# Get script directory and source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

echo "⚙️  Testing GET /v1/config..."
echo ""

# Make the request
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -H "Authorization: Bearer ${TOKEN}" \
  "${API_BASE_URL}/v1/config")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "✅ Success (HTTP 200)"
  echo ""
  echo "$BODY" | python3 -m json.tool
  exit 0
elif [ "$HTTP_CODE" = "401" ]; then
  echo "❌ Failed (HTTP 401 - Unauthorized)"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
else
  echo "❌ Failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
