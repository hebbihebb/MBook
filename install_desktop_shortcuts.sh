#!/usr/bin/env bash
# Install desktop shortcuts with the current repo path baked in.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

mkdir -p "$APP_DIR"

install_template() {
  local template="$1"
  local output="$2"

  if [[ ! -f "$template" ]]; then
    echo "Template not found: $template" >&2
    return 1
  fi

  sed "s|@MBOOK_ROOT@|$REPO_ROOT|g" "$template" > "$output"
}

install_template "$REPO_ROOT/mbook-webui.desktop.in" "$APP_DIR/mbook-webui.desktop"
install_template "$REPO_ROOT/mbook-electron.desktop.in" "$APP_DIR/mbook-electron.desktop"

echo "Desktop entries installed to $APP_DIR"
