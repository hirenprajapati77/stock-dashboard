#!/usr/bin/env bash
set -euo pipefail

TARGET_BRANCH="${1:-work}"
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if ! git remote get-url origin >/dev/null 2>&1; then
  echo "origin remote is not configured."
  exit 1
fi

echo "Fetching latest refs from origin..."
git fetch origin

echo "Merging origin/${TARGET_BRANCH} into ${CURRENT_BRANCH}..."
if git merge "origin/${TARGET_BRANCH}"; then
  echo "Merge completed without conflicts."
  exit 0
fi

echo
echo "Conflicts detected. Resolve these files first:"
printf ' - %s\n' \
  backend/app/services/rotation_alerts.py \
  backend/app/services/screener_service.py \
  backend/app/services/sector_service.py \
  frontend/LABEL_REPLACEMENTS.md \
  frontend/dashboard.js \
  frontend/rotation.js

echo
echo "After resolving:"
echo "  git add <resolved-files>"
echo "  git commit -m 'Resolve PR #4 merge conflicts'"
