#!/usr/bin/env bash
# Launch the WebUI server from the repo root.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$REPO_ROOT/venv_py311/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "Virtualenv not found at $VENV_PY. Please install deps first."
  exit 1
fi

cd "$REPO_ROOT"
exec "$VENV_PY" webview_ui/webview_server.py "$@"
