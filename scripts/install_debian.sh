#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/AguacatIA"
REPO_URL="https://github.com/TitoTB/AguacatIA.git"
SERVICE_FILE="/etc/systemd/system/aguacatia.service"
PORT="${PORT:-8020}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este instalador como root."
  exit 1
fi

apt update
apt install -y git python3 python3-venv

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" pull
else
  rm -rf "$APP_DIR"
  git clone "$REPO_URL" "$APP_DIR"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

mkdir -p "$APP_DIR/data"

cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=AguacatIA Telegram bot and admin panel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable aguacatia
systemctl restart aguacatia

echo
echo "AguacatIA instalado."
echo "Abre: http://IP_DEL_SERVIDOR:$PORT"
echo "Logs: journalctl -u aguacatia -f"

