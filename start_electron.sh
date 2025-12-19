#!/usr/bin/env bash
# Launch the Electron app from the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ELECTRON_CMD="$REPO_ROOT/node_modules/.bin/electron"
MAIN_JS="$REPO_ROOT/webview_ui/main.js"

if [[ ! -x "$ELECTRON_CMD" ]]; then
  echo "Electron binary not found at $ELECTRON_CMD. Run npm install first."
  exit 1
fi

cd "$REPO_ROOT"
exec "$ELECTRON_CMD" "$MAIN_JS" "$@"
