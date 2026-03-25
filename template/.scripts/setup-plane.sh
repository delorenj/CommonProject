#!/usr/bin/env bash
# Creates a Plane project in the 33god workspace and writes .plane.json
set -euo pipefail

PROJECT_NAME="${1:?Usage: setup-plane.sh <project_name> [description]}"
PROJECT_DESC="${2:-}"
PLANE_API="https://plane.delo.sh/api/v1"
WORKSPACE="33god"

# Derive identifier: first 4 chars of name, uppercased, alphanumeric only
IDENTIFIER=$(echo "${PROJECT_NAME}" | tr -cd '[:alnum:]' | head -c4 | tr '[:lower:]' '[:upper:]')
[ ${#IDENTIFIER} -lt 2 ] && IDENTIFIER="${IDENTIFIER}XX"

# Check for API key
if [ -z "${PLANE_33GOD_API_KEY:-}" ]; then
    echo "WARNING: PLANE_33GOD_API_KEY not set. Writing placeholder .plane.json"
    echo "  Set the key and re-run: bash .scripts/setup-plane.sh '${PROJECT_NAME}' '${PROJECT_DESC}'"
    cat > .plane.json <<EOF
{
  "workspace": "${WORKSPACE}",
  "project_id": "PLACEHOLDER",
  "project_identifier": "${IDENTIFIER}"
}
EOF
    exit 0
fi

# Create project via Plane API
RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${PLANE_API}/workspaces/${WORKSPACE}/projects/" \
    -H "X-API-Key: ${PLANE_33GOD_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"${PROJECT_NAME}\",
        \"description\": \"${PROJECT_DESC}\",
        \"identifier\": \"${IDENTIFIER}\",
        \"network\": 2
    }" 2>/dev/null)

HTTP_CODE=$(echo "${RESPONSE}" | tail -1)
BODY=$(echo "${RESPONSE}" | sed '$d')

if [ "${HTTP_CODE}" -ge 200 ] && [ "${HTTP_CODE}" -lt 300 ]; then
    PROJECT_ID=$(echo "${BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null || echo "")
    ACTUAL_IDENT=$(echo "${BODY}" | python3 -c "import sys,json; print(json.load(sys.stdin)['identifier'])" 2>/dev/null || echo "${IDENTIFIER}")

    if [ -n "${PROJECT_ID}" ]; then
        cat > .plane.json <<EOF
{
  "workspace": "${WORKSPACE}",
  "project_id": "${PROJECT_ID}",
  "project_identifier": "${ACTUAL_IDENT}"
}
EOF
        echo "Plane project created: ${ACTUAL_IDENT} (${PROJECT_ID})"
    else
        echo "WARNING: Could not parse project ID from response. Writing placeholder."
        cat > .plane.json <<EOF
{
  "workspace": "${WORKSPACE}",
  "project_id": "PLACEHOLDER",
  "project_identifier": "${IDENTIFIER}"
}
EOF
    fi
else
    echo "WARNING: Plane API returned ${HTTP_CODE}. Writing placeholder .plane.json"
    echo "  Response: ${BODY}"
    cat > .plane.json <<EOF
{
  "workspace": "${WORKSPACE}",
  "project_id": "PLACEHOLDER",
  "project_identifier": "${IDENTIFIER}"
}
EOF
fi
