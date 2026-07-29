#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# desensitize version bump + tag + push (triggers CI to build package)
#
# Usage:
#   ./scripts/update_version.sh           # bump patch (default)
#   ./scripts/update_version.sh minor     # bump minor
#   ./scripts/update_version.sh major     # bump major
# =============================================================================

cd "$(dirname "${BASH_SOURCE[0]}")/.."

VERSION_FILE="ictrek.app/VERSION"
TAG_PREFIX="vos-desensitize-v"

BUMP_TYPE="${1:-patch}"

log() { echo "[INFO] $*"; }
die() { echo "[ERROR] $*" >&2; exit 1; }

# Ensure clean working tree
if ! git diff --quiet || ! git diff --cached --quiet; then
  die "Working tree not clean. Please commit your changes first."
fi

# Read current version
CURRENT_VERSION="$(tr -d '[:space:]' < "$VERSION_FILE")"
log "Current version: $CURRENT_VERSION"

# Bump version
IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT_VERSION"
case "$BUMP_TYPE" in
  major)   MAJOR=$((MAJOR + 1)); MINOR=0; PATCH=0 ;;
  minor)   MINOR=$((MINOR + 1)); PATCH=0 ;;
  patch)   PATCH=$((PATCH + 1)) ;;
  *) die "Unknown bump type: $BUMP_TYPE" ;;
esac
NEW_VERSION="${MAJOR}.${MINOR}.${PATCH}"
log "New version: $NEW_VERSION"

# Write new version
echo "$NEW_VERSION" > "$VERSION_FILE"
git add "$VERSION_FILE"

# Commit version bump
git commit -m "chore: bump desensitize to ${NEW_VERSION}"

# Create tags
VOS_TAG="${TAG_PREFIX}${NEW_VERSION}"
PUBLIC_TAG="v${NEW_VERSION}"

git tag "$VOS_TAG"
git tag "$PUBLIC_TAG"

log "Created tags: ${VOS_TAG}, ${PUBLIC_TAG}"

# Push
git push origin HEAD
git push origin "$VOS_TAG"
git push origin "$PUBLIC_TAG"

log "Pushed. CI will build the package when the ${VOS_TAG} tag is processed."
