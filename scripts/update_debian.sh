#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/AguacatIA"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

git_auth() {
  if [ -n "$GITHUB_TOKEN" ]; then
    git -c http.extraHeader="Authorization: Bearer $GITHUB_TOKEN" "$@"
  else
    git "$@"
  fi
}

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este actualizador como root."
  exit 1
fi

git_auth -C "$APP_DIR" pull
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
systemctl restart aguacatia

echo "AguacatIA actualizado."
