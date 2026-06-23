# AguacatIA

Bot privado de Telegram con panel web local, permisos por nivel y sistema de skills extensible.

## Que incluye esta base

- Panel web local con primera configuracion de contrasena.
- SQLite en `data/aguacatia.sqlite`.
- Token de Telegram y secretos gestionados desde el panel.
- Niveles dinamicos de acceso, con `Publico`, `Aguacatec Friend` y `Aguacatec Lover` creados por defecto.
- Skills activables y asignables a un nivel minimo.
- Bot Telegram con polling, comandos y menu de comandos.
- Skill inicial `/dispositivo` contra la API de BDevices:
  `POST /api/agent/devices/search`.
- Instalador Debian y creador/actualizador de LXC para Proxmox.

## Desarrollo local

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
```

Abre:

```text
http://localhost:8020
```

En el primer acceso, crea la contrasena admin. Despues configura:

- token del bot de Telegram
- owner Telegram ID
- URL y token de agente de BDevices
- proveedor IA futuro: Ollama, OpenAI o Gemini

## Instalacion en servidor Debian

En un LXC o VM Debian:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/install_debian.sh)"
```

Despues abre:

```text
http://IP_DEL_SERVIDOR:8020
```

## Crear LXC automaticamente desde Proxmox

Desde la shell del host Proxmox:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/proxmox_create_lxc.sh)"
```

Opcionalmente puedes elegir parametros:

```bash
CTID=140 HOSTNAME=AguacatIA MEMORY=1024 DISK=8 PORT=8020 bash -c "$(curl -fsSL https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/proxmox_create_lxc.sh)"
```

Si tu almacenamiento no se llama `local-lvm`, indica otro:

```bash
ROOTFS_STORAGE=local bash -c "$(curl -fsSL https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/proxmox_create_lxc.sh)"
```

## Actualizar un LXC existente desde Proxmox

Cuando haya una nueva version publicada en GitHub, no recrees el contenedor:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/proxmox_update_lxc.sh)"
```

Si necesitas indicar el ID manualmente:

```bash
CTID=140 bash -c "$(curl -fsSL https://raw.githubusercontent.com/TitoTB/AguacatIA/main/scripts/proxmox_update_lxc.sh)"
```

## Servicio

```bash
systemctl status aguacatia
systemctl restart aguacatia
journalctl -u aguacatia -f
```

## Crear nuevas skills

1. Crea una clase en `app/skills/`.
2. Define `definition = SkillDefinition(...)`.
3. Implementa `async def handle(self, context)`.
4. Registrala en `app/skills/__init__.py`.
5. Reinicia el servicio. Aparecera en el panel para activar/desactivar y asignar nivel.

