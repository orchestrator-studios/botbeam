#!/usr/bin/env bash
set -euo pipefail

export AWS_PROFILE=copilot
export AWS_REGION=us-east-2

# Bump version
VERSION_FILE="$(dirname "$0")/VERSION"
CURRENT=$(cat "$VERSION_FILE")
NEXT=$(awk "BEGIN {printf \"%.1f\", $CURRENT + 0.1}")
echo "$NEXT" > "$VERSION_FILE"

echo "=== BotBeam Deploy v${NEXT} ==="
echo ""

# Deploy via Copilot
echo "Deploying..."
copilot svc deploy --name web --env prod

echo ""
echo "=== Deploy complete ==="
echo "Version: $NEXT"
echo "Site:    https://botbeam.ironcliff.ai"
