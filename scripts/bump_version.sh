#!/bin/bash
# Bumps the project version in VERSION (semantic versioning).
#
#   scripts/bump_version.sh patch   1.0.0 -> 1.0.1   small fixes/tweaks (default)
#   scripts/bump_version.sh minor   1.0.1 -> 1.1.0   moderate: a new feature or notable change
#   scripts/bump_version.sh major   1.1.0 -> 2.0.0   big/breaking changes
#
# Run it before each commit and include VERSION in that commit (see the
# "Versioning" section of CLAUDE.md).
set -e
cd "$(dirname "$0")/.."

level="${1:-patch}"
current="$(tr -d '[:space:]' < VERSION)"
IFS=. read -r major minor patch <<< "$current"

case "$level" in
    patch) patch=$((patch + 1)) ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    major) major=$((major + 1)); minor=0; patch=0 ;;
    *) echo "usage: $0 [patch|minor|major]" >&2; exit 1 ;;
esac

echo "$major.$minor.$patch" > VERSION
echo "$current -> $major.$minor.$patch"
