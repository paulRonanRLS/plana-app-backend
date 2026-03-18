#!/usr/bin/env bash
#
# Test POST /v1/recipes endpoint
#

set -e

# Get script directory and source common utilities
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source "$SCRIPT_DIR/_common.sh"

echo "🍳 Testing POST /v1/recipes..."
echo ""

# Create minimal valid recipe payload
PAYLOAD=$(cat <<'EOF'
{
  "title": "Quick Toast with Butter",
  "description": "Simple breakfast toast",
  "source_type": "manual",
  "base_servings": 1,
  "prep_time": 2,
  "cook_time": 3,
  "total_time": 5,
  "ingredients": [
    {
      "name": "bread",
      "quantity": 2,
      "unit": "slices",
      "sort_order": 0
    },
    {
      "name": "butter",
      "quantity": 1,
      "unit": "tbsp",
      "sort_order": 1
    }
  ],
  "steps": [
    {
      "step_number": 1,
      "instruction": "Toast the bread until golden"
    },
    {
      "step_number": 2,
      "instruction": "Spread butter on hot toast"
    },
    {
      "step_number": 3,
      "instruction": "Serve immediately"
    }
  ],
  "tags": ["breakfast", "quick", "simple"]
}
EOF
)

echo "Creating recipe: Quick Toast with Butter"
echo ""
echo "Making request..."

# Make the request
RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "${API_BASE_URL}/v1/recipes")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "201" ]; then
  echo "✅ Success (HTTP 201)"
  echo ""
  echo "$BODY" | python3 -m json.tool
  echo ""

  # Extract and display key fields
  RECIPE_ID=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', 'N/A'))" 2>/dev/null)
  TITLE=$(echo "$BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', 'N/A'))" 2>/dev/null)
  NUM_INGREDIENTS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('ingredients', [])))" 2>/dev/null)
  NUM_STEPS=$(echo "$BODY" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('steps', [])))" 2>/dev/null)

  echo "📋 Summary:"
  echo "   Recipe ID: $RECIPE_ID"
  echo "   Title: $TITLE"
  echo "   Ingredients: $NUM_INGREDIENTS"
  echo "   Steps: $NUM_STEPS"
  echo ""
  echo "💡 To view this recipe:"
  echo "   curl -H \"Authorization: Bearer \$TOKEN\" ${API_BASE_URL}/v1/recipes/${RECIPE_ID}"
else
  echo "❌ Failed (HTTP ${HTTP_CODE})"
  echo ""
  echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  exit 1
fi
