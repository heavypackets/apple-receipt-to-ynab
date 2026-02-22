#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python3"

if [[ ! -x "$PYTHON_BIN" ]]; then
  python3 -m venv "$VENV_DIR"
fi

# Use --ignore-installed so a broken editable metadata state (missing RECORD)
# does not block developer test runs. Use --no-deps to keep test runs
# offline-friendly and avoid unnecessary resolver/network calls.
"$PYTHON_BIN" -m pip install --ignore-installed --no-deps --no-build-isolation -e "$ROOT_DIR[dev]"
"$PYTHON_BIN" -m pytest "$@"
