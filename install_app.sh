#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v pipx >/dev/null 2>&1; then
  echo "Error: pipx is required for installation."
  echo "Install pipx first, then run:"
  echo "  pipx ensurepath"
  echo "  ./install_app.sh"
  exit 1
fi

pipx install --force "$ROOT_DIR"
