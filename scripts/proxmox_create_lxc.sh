#!/usr/bin/env bash
set -euo pipefail

echo "Arrancando instalador AguacatIA para Proxmox..."

INSTALL_URL="https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/install_debian.sh"

CTID="${CTID:-}"
HOSTNAME="${HOSTNAME:-AguacatIA}"
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
ROOTFS_STORAGE="${ROOTFS_STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
MEMORY="${MEMORY:-1024}"
CORES="${CORES:-1}"
DISK="${DISK:-8}"
PORT="${PORT:-8020}"
PASSWORD="${PASSWORD:-}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Ejecuta este script como root en el host Proxmox."
  exit 1
fi

if ! command -v pct >/dev/null 2>&1; then
  echo "No encuentro 'pct'. Este script debe ejecutarse en el host Proxmox, no dentro de un LXC."
  exit 1
fi

if [ -z "$CTID" ]; then
  CTID="$(pvesh get /cluster/nextid)"
fi

if pct status "$CTID" >/dev/null 2>&1; then
  echo "Ya existe un contenedor con CTID=$CTID. Elige otro con: CTID=123 bash ..."
  exit 1
fi

if ! pvesm status | awk '{print $1}' | grep -qx "$ROOTFS_STORAGE"; then
  echo "No existe el storage ROOTFS_STORAGE=$ROOTFS_STORAGE."
  echo "Storages disponibles:"
  pvesm status
  exit 1
fi

if ! pvesm status | awk '{print $1}' | grep -qx "$TEMPLATE_STORAGE"; then
  echo "No existe el storage TEMPLATE_STORAGE=$TEMPLATE_STORAGE."
  pvesm status
  exit 1
fi

if [ -z "$PASSWORD" ]; then
  PASSWORD="AguacatIA$(date +%s)"
fi

echo "AguacatIA Proxmox installer"
echo "CTID: $CTID"
echo "Hostname: $HOSTNAME"
echo "Template storage: $TEMPLATE_STORAGE"
echo "Rootfs storage: $ROOTFS_STORAGE"
echo "Bridge: $BRIDGE"
echo "Memory: ${MEMORY}MB"
echo "Cores: $CORES"
echo "Disk: ${DISK}GB"
echo "Port: $PORT"
echo

echo "Actualizando lista de plantillas..."
pveam update

TEMPLATE="$(pveam available --section system | awk '$2 ~ /debian-12-standard.*amd64.tar.zst/ {print $2; exit}')"
if [ -z "$TEMPLATE" ]; then
  echo "No encuentro plantilla Debian 12 en pveam."
  exit 1
fi

if [ ! -f "/var/lib/vz/template/cache/$TEMPLATE" ]; then
  echo "Descargando plantilla $TEMPLATE..."
  pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
fi

echo "Creando LXC $CTID ($HOSTNAME)..."
pct create "$CTID" "$TEMPLATE_STORAGE:vztmpl/$TEMPLATE" \
  --hostname "$HOSTNAME" \
  --password "$PASSWORD" \
  --cores "$CORES" \
  --memory "$MEMORY" \
  --rootfs "$ROOTFS_STORAGE:$DISK" \
  --net0 "name=eth0,bridge=$BRIDGE,ip=dhcp" \
  --ostype debian \
  --unprivileged 1 \
  --features nesting=1 \
  --onboot 1 \
  --start 1

echo "Esperando red dentro del contenedor..."
for _ in $(seq 1 60); do
  if pct exec "$CTID" -- bash -lc "getent hosts deb.debian.org >/dev/null 2>&1"; then
    break
  fi
  sleep 2
done

echo "Instalando AguacatIA dentro del LXC..."
if [ -n "$GITHUB_TOKEN" ]; then
  pct exec "$CTID" -- bash -lc "apt update && apt install -y curl ca-certificates && export GITHUB_TOKEN='$GITHUB_TOKEN' && PORT=$PORT bash -c \"\$(curl -H 'Authorization: Bearer $GITHUB_TOKEN' -fsSL $INSTALL_URL)\""
else
  pct exec "$CTID" -- bash -lc "apt update && apt install -y curl ca-certificates && PORT=$PORT bash -c \"\$(curl -fsSL $INSTALL_URL)\""
fi

IP="$(pct exec "$CTID" -- bash -lc "hostname -I | awk '{print \$1}'" | tr -d '\r')"

echo
echo "AguacatIA instalado."
echo "CTID: $CTID"
echo "Hostname: $HOSTNAME"
echo "Root password: $PASSWORD"
echo "URL: http://$IP:$PORT"
echo
echo "Comandos utiles:"
echo "  pct enter $CTID"
echo "  pct exec $CTID -- systemctl status aguacatia"
echo "  pct exec $CTID -- journalctl -u aguacatia -f"
