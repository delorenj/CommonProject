#!/bin/bash
# =============================================================================
# create-plane-project.sh
# Creates a project in Plane and outputs the project ID
# =============================================================================
# Usage: ./scripts/create-plane-project.sh <workspace> <project_name> <identifier>
#
# Environment Variables:
#   PLANE_API_KEY - Required. Plane API key (get from Plane workspace settings)
#   PLANE_BASE_URL - Optional. Defaults to https://plane.delo.sh
#
# Output: Project ID (UUID) on success, non-zero exit on failure
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
WORKSPACE="${1:-}"
PROJECT_NAME="${2:-}"
PROJECT_IDENTIFIER="${3:-}"

# Validate arguments
if [[ -z "$WORKSPACE" ]] || [[ -z "$PROJECT_NAME" ]] || [[ -z "$PROJECT_IDENTIFIER" ]]; then
    echo -e "${RED}Error: Missing required arguments${NC}" >&2
    echo "Usage: $0 <workspace> <project_name> <identifier>" >&2
    echo "  workspace       - Plane workspace slug (e.g., 33god)" >&2
    echo "  project_name    - Display name for the project" >&2
    echo "  identifier      - 2+ char identifier for tickets (e.g., MYPRJ)" >&2
    exit 1
fi

# Validate identifier length
if [[ ${#PROJECT_IDENTIFIER} -lt 2 ]]; then
    echo -e "${RED}Error: Identifier must be at least 2 characters${NC}" >&2
    exit 1
fi

# Check for API key
if [[ -z "${PLANE_API_KEY:-}" ]]; then
    echo -e "${RED}Error: PLANE_API_KEY environment variable is not set${NC}" >&2
    echo "Get your API key from: https://plane.delo.sh/<workspace>/settings/api-tokens/" >&2
    exit 1
fi

# Configuration
PLANE_BASE_URL="${PLANE_BASE_URL:-https://plane.delo.sh}"

# Status logs go to stderr so stdout stays clean for the UUID (the data).
{
    echo -e "${YELLOW}Creating Plane project...${NC}"
    echo "  Workspace:  $WORKSPACE"
    echo "  Name:       $PROJECT_NAME"
    echo "  Identifier: $PROJECT_IDENTIFIER"
} >&2

# Create project via Plane API
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "${PLANE_BASE_URL}/api/v1/workspaces/${WORKSPACE}/projects/" \
    -H "X-Api-Key: ${PLANE_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"${PROJECT_NAME}\", \"identifier\": \"${PROJECT_IDENTIFIER}\"}")

# Parse response and HTTP code
HTTP_BODY=$(echo "$RESPONSE" | sed '$d')
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

# On 400/409, the project likely already exists. Try to resolve it by identifier
# via GET so callers get the existing UUID instead of having to paste one manually.
# Note: this walks the first page of results. If a workspace has enough projects
# to paginate past the match, add pagination here.
if [[ "$HTTP_CODE" -eq 400 ]] || [[ "$HTTP_CODE" -eq 409 ]]; then
    echo -e "${YELLOW}⚠ POST returned HTTP $HTTP_CODE — checking if project already exists...${NC}" >&2

    LIST_RESPONSE=$(curl -s -w "\n%{http_code}" -X GET \
        "${PLANE_BASE_URL}/api/v1/workspaces/${WORKSPACE}/projects/" \
        -H "X-Api-Key: ${PLANE_API_KEY}" \
        -H "Content-Type: application/json")
    LIST_BODY=$(echo "$LIST_RESPONSE" | sed '$d')
    LIST_CODE=$(echo "$LIST_RESPONSE" | tail -n1)

    if [[ "$LIST_CODE" -ge 200 ]] && [[ "$LIST_CODE" -lt 300 ]]; then
        EXISTING_ID=$(echo "$LIST_BODY" | PLANE_IDENT="$PROJECT_IDENTIFIER" python3 -c "
import json, os, sys
target = os.environ['PLANE_IDENT'].upper()
data = json.load(sys.stdin)
items = data.get('results', data) if isinstance(data, dict) else data
for p in items or []:
    if str(p.get('identifier', '')).upper() == target:
        print(p['id'])
        break
" 2>/dev/null || true)

        if [[ -n "$EXISTING_ID" ]]; then
            echo -e "${GREEN}✓ Found existing project matching identifier ${PROJECT_IDENTIFIER}${NC}" >&2
            echo -e "  Project ID: ${GREEN}${EXISTING_ID}${NC}" >&2
            echo "$EXISTING_ID"
            exit 0
        fi
    fi
    # Fall through: lookup didn't resolve it, surface the original POST error.
fi

# Check for errors (original POST failed and lookup didn't save us)
if [[ "$HTTP_CODE" -lt 200 ]] || [[ "$HTTP_CODE" -ge 300 ]]; then
    echo -e "${RED}Error: Plane API returned HTTP $HTTP_CODE${NC}" >&2
    echo "$HTTP_BODY" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('detail', d))" 2>/dev/null || echo "$HTTP_BODY" >&2
    exit 1
fi

# Extract project ID from successful POST
PROJECT_ID=$(echo "$HTTP_BODY" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

echo -e "${GREEN}✓ Project created successfully${NC}" >&2
echo -e "  Project ID: ${GREEN}${PROJECT_ID}${NC}" >&2

# Output just the ID on stdout for capture
echo "$PROJECT_ID"
