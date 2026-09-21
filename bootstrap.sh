#!/bin/bash
# One-command bootstrap for a freshly flashed Pi: clones this repo and runs
# install.sh. Meant to be run via curl, e.g. from the Pi over SSH:
#
#   bash <(curl -fsSL https://raw.githubusercontent.com/joecan2/groove-tracker/main/bootstrap.sh)
#
# Replace YOUR_GITHUB_USERNAME below (and in the URL above, once you've
# pushed this repo) with your actual GitHub username/repo.

set -e

REPO_URL="https://github.com/joecan2/groove-tracker.git"
CLONE_DIR="$HOME/groove-tracker"

echo "=== Groove Tracker bootstrap ==="

if [ -d "$CLONE_DIR" ]; then
    echo "$CLONE_DIR already exists — pulling latest instead of cloning."
    git -C "$CLONE_DIR" pull
else
    echo "Cloning $REPO_URL to $CLONE_DIR..."
    git clone "$REPO_URL" "$CLONE_DIR"
fi

cd "$CLONE_DIR"
exec bash install.sh
