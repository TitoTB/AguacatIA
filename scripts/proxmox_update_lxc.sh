#!/usr/bin/env bash
set -euo pipefail

CTID="${CTID:-}"
HOSTNAME="${HOSTNAME:-AguacatIA}"
UPDATE_URL="https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/update_debian.sh"
PORT="${PORT:-8020}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este script como root en el host Proxmox."
  exit 1
fi

if ! command -v pct >/dev/null 2>&1; then
  echo "No encuentro 'pct'. Este script debe ejecutarse en el host Proxmox."
  exit 1
fi

if [ -z "$CTID" ]; then
  CTID="$(pct list | awk -v name="$HOSTNAME" 'tolower($3) == tolower(name) {print $1; exit}')"
fi

if [ -z "$CTID" ]; then
  echo "No encuentro un LXC llamado $HOSTNAME."
  echo "Indica el ID manualmente: CTID=123 bash -c \"\$(curl -fsSL URL)\""
  pct list
  exit 1
fi

echo "Actualizando AguacatIA en CTID=$CTID..."
pct exec "$CTID" -- bash -lc "apt update && apt install -y curl ca-certificates && bash -c \"\$(curl -fsSL $UPDATE_URL)\""

IP="$(pct exec "$CTID" -- bash -lc "hostname -I | awk '{print \$1}'" | tr -d '\r')"
echo
echo "AguacatIA actualizado."
echo "URL: http://$IP:$PORT"

