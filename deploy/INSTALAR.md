# Instalación en el PC Fedora

Guía para instalar el buscador en el mismo PC donde corre Hermes y dejarlo corriendo cada
30 minutos con systemd de usuario. Todo vive bajo `$HOME`, así que **no hace falta tocar
SELinux**. Los comandos se ejecutan con el usuario de Hermes (no con root), salvo los que
llevan `sudo`.

Orden: instalar → configurar → migrar y sembrar → fase de prueba (24 h, chat de prueba) →
paso a producción (con aprobación).

## 1. Requisitos

```bash
# uv (instala también Python 3.12 por su cuenta). Las unidades systemd esperan uv en
# ~/.local/bin/uv, que es donde lo deja este instalador.
curl -LsSf https://astral.sh/uv/install.sh | sh
~/.local/bin/uv --version

sudo dnf install -y git sqlite   # sqlite solo para diagnóstico
```

## 2. Código

```bash
git clone https://github.com/Jordy-Lv/JobScrapper_TG.git ~/buscador-vacantes
cd ~/buscador-vacantes
~/.local/bin/uv sync --frozen
~/.local/bin/uv run pytest -q          # deben pasar todas (no usan red)
```

Si el repositorio es privado, `git clone` pedirá credenciales: usar `gh auth login` o un
token personal de GitHub.

## 3. Secretos (`.env`)

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

| Variable | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | **Dejar vacío**: se lee del `.env` de Hermes en cada corrida (así una rotación del token en Hermes no rompe el buscador). |
| `TELEGRAM_CHAT_ID` | `-1004429829042` (canal real) |
| `TELEGRAM_CHAT_PRUEBA` | `5051574309` (chat privado con el bot) |
| `DEEPSEEK_API_KEY` | clave de DeepSeek |
| `HEALTHCHECK_URL` | URL de ping del paso 4 |

Comprobar que el token de Hermes está donde lo busca `config.yaml`
(`telegram.token_hermes`, por defecto `~/.hermes/.env` con la variable `TELEGRAM_BOT_TOKEN`):

```bash
grep -c '^TELEGRAM_BOT_TOKEN=' ~/.hermes/.env    # debe imprimir 1
```

Si el archivo o la variable tienen otro nombre, corregir `telegram.token_hermes` en
`config.yaml` (o poner el token en `TELEGRAM_BOT_TOKEN` del `.env` propio).

## 4. Heartbeat en healthchecks.io

1. Crear un check llamado `buscador-vacantes` con **periodo 30 min** y **gracia 45 min**.
2. Configurar la notificación (correo o Telegram) en la integración de healthchecks.io.
3. Copiar la URL de ping (`https://hc-ping.com/<uuid>`) en `HEALTHCHECK_URL`.

Cada corrida hace ping a `/start` al empezar, a la URL al terminar bien y a `/fail` si hay
un error interno. Si las corridas dejan de llegar, healthchecks.io avisa.

## 5. Pruebas manuales

```bash
cd ~/buscador-vacantes
uv() { ~/.local/bin/uv "$@"; }   # atajo para esta sesión

uv run buscador.py --dry-run --fuente linkedin      # repetir con computrabajo, elempleo,
uv run buscador.py --dry-run --fuente magneto       #   magneto y getonboard
uv run buscador.py --simular-incidente linkedin:bloqueo --dry-run
uv run buscador.py --simular-incidente computrabajo:cambio_html   # llega al chat de prueba
```

## 6. Migración del historial de Hermes y siembra

```bash
uv run buscador.py migrar     # lee ~/.hermes/cron/output/historial_vacantes.json
uv run buscador.py migrar     # segunda vez: 0 importadas (es idempotente)
uv run buscador.py --seed     # marca lo que hay hoy como visto, sin enviar
```

Sin la migración o la siembra el buscador **se niega a enviar**, para no inundar el canal.

## 7. Fase de prueba: timers apuntando al chat de prueba

```bash
mkdir -p ~/.config/systemd/user/buscador.service.d ~/.config/systemd/user/buscador-resumen.service.d
cp deploy/buscador.service deploy/buscador.timer \
   deploy/buscador-resumen.service deploy/buscador-resumen.timer ~/.config/systemd/user/
# Drop-ins de la fase de prueba: las corridas y el resumen van al chat de prueba
cp deploy/prueba/buscador.service.d.conf ~/.config/systemd/user/buscador.service.d/prueba.conf
cp deploy/prueba/buscador-resumen.service.d.conf ~/.config/systemd/user/buscador-resumen.service.d/prueba.conf

systemd-analyze --user verify ~/.config/systemd/user/buscador*.service ~/.config/systemd/user/buscador*.timer
systemctl --user daemon-reload
systemctl --user enable --now buscador.timer buscador-resumen.timer

# Correr sin sesión iniciada (tras un reinicio, sin que nadie entre al PC)
sudo loginctl enable-linger "$USER"
```

Primera corrida a mano para no esperar al timer:

```bash
systemctl --user start buscador.service
journalctl --user -u buscador -n 50 --no-pager
```

### Que el PC no se suspenda

Un PC suspendido no corre nada. El PC actual es un **portátil con XFCE** (no GNOME): la
suspensión por inactividad ya está en "nunca", pero puede suspenderse al cerrar la tapa o
desde el menú. Lo más robusto es bloquear la suspensión a nivel de systemd, que cubre
cualquier escritorio, la tapa y el menú (deshacer con `unmask`):

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

Para comprobar cuándo se suspendió: `journalctl -b -u systemd-logind | grep -i suspend`.

Con GNOME, la alternativa sin `sudo` para el usuario es:

```bash
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
```

Si el PC se apaga o suspende igualmente, `Persistent=true` hace una sola corrida de
recuperación al volver, y el filtro de 15 días evita publicar vacantes viejas.

## 8. Verificación

```bash
systemctl --user list-timers 'buscador*'        # próximas ejecuciones
systemctl --user status buscador.service
journalctl --user -u buscador --since today
tail -f logs/$(date +%F).log
```

- healthchecks.io debe estar en verde.
- Reiniciar el PC **sin iniciar sesión** y comprobar en `journalctl` y healthchecks.io que la
  corrida se ejecuta (linger + `Persistent=true`).
- Desconectar la red durante una corrida: solo debe aparecer `red:sin_conexion`, sin
  cooldowns; al volver llega "⚠️ El PC estuvo sin internet de … a …".
- Detener el timer 90 min (`systemctl --user stop buscador.timer`) y comprobar que
  healthchecks.io avisa; luego `systemctl --user start buscador.timer`.

Dejar correr **24 h en paralelo con Hermes** y comparar cantidad, duplicados y relevancia
entre el chat de prueba y el canal.

## 9. Paso a producción (solo con aprobación explícita)

El orden importa: si una corrida apuntara al canal antes de `promover-prueba`, reenviaría
todo lo que ya salió en el chat de prueba.

```bash
cd ~/buscador-vacantes
# 1. Detener el timer (si hay una corrida en curso, esperar a que termine)
systemctl --user stop buscador.timer
systemctl --user is-active buscador.service   # debe decir "inactive"

# 2. Lo que ya salió en el chat de prueba no se reenvía al canal. Si falla (código 1),
#    hay una corrida activa: esperar y repetir. No seguir hasta que funcione.
~/.local/bin/uv run buscador.py promover-prueba

# 3. Quitar los drop-ins de prueba y reactivar el timer apuntando al canal real
rm ~/.config/systemd/user/buscador.service.d/prueba.conf \
   ~/.config/systemd/user/buscador-resumen.service.d/prueba.conf
systemctl --user daemon-reload
systemctl --user start buscador.timer
```

4. **Pausar (no borrar)** en Hermes el cronjob `d6381ce58395` ("Buscador Empleo Carlos
   Mario") y su pre-run `send_encabezado.py`, con el comando de pausa de Hermes
   (`hermes cron --help` muestra cómo). Comprobar que figura pausado.
5. Verificar que el siguiente envío real llega al canal:
   `journalctl --user -u buscador -f`.

## 10. Operación

| Necesidad | Comando |
|---|---|
| Ver próximas corridas | `systemctl --user list-timers 'buscador*'` |
| Últimas corridas | `journalctl --user -u buscador -n 200 --no-pager` |
| Log del día | `less ~/buscador-vacantes/logs/$(date +%F).log` |
| Corrida manual | `systemctl --user start buscador.service` |
| Resumen manual | `~/.local/bin/uv run buscador.py --dry-run resumen` |
| Cooldowns vigentes | `sqlite3 data/vacantes.db "select * from fuentes_estado"` |
| Incidentes abiertos | `sqlite3 data/vacantes.db "select fuente, tipo, abierto_desde from incidentes where cerrado_en is null"` |
| Últimas corridas (métricas) | `sqlite3 data/vacantes.db "select id, inicio, modo, crudas, enviadas, error from corridas order by id desc limit 10"` |
| Desactivar una fuente | `activa: false` en `config.yaml` (efecto en la siguiente corrida) |
| Ajustar filtros o palabras clave | editar `config.yaml`; probar con `--dry-run` |

### Actualizar

```bash
cd ~/buscador-vacantes
git pull
~/.local/bin/uv sync --frozen
~/.local/bin/uv run pytest -q
# Si cambiaron las unidades en deploy/: copiarlas de nuevo y `systemctl --user daemon-reload`
```

### Rollback

```bash
systemctl --user disable --now buscador.timer buscador-resumen.timer
```

Luego reactivar en Hermes el cronjob `d6381ce58395` y `send_encabezado.py`. El estado
(`data/vacantes.db`) se conserva para cuando se vuelva a activar el buscador.

## 11. Asistente de postulación (opcional)

El asistente (bot de Telegram, API para la extensión y CV adaptado) corre como **otro servicio**
de systemd de usuario, aparte del buscador: si se detiene, el buscador sigue publicando igual.
Viene desactivado (`asistente.activo: false`). Orden: instalar → piloto privado → piloto con
invitados → tienda de Edge → `enlace_canal: true`. Lo que ven los usuarios está en
`docs/guia-usuario.md`.

### 11.1 Bot en BotFather

1. En Telegram, hablar con [@BotFather](https://t.me/BotFather) → `/newbot`. Debe ser un bot
   **nuevo**, distinto del de Hermes. Anotar el token y el usuario (sin `@`).
2. Agregar el bot al **grupo privado** (el de `TELEGRAM_CHAT_ID`) como **administrador sin
   ningún permiso**: lo necesita para comprobar con `getChatMember` quién es miembro.
3. Averiguar el id de Telegram del administrador (el del dueño): escribirle al bot
   [@userinfobot](https://t.me/userinfobot).

### 11.2 Clave maestra y su respaldo

La clave maestra cifra las claves de Gemini y los correos de las cuentas de los usuarios.

```bash
cd ~/buscador-vacantes
~/.local/bin/uv sync --frozen --group asistente
~/.local/bin/uv run --group asistente buscador.py asistente generar-clave
```

Pegar el resultado y el token del bot en `.env`:

```bash
ASISTENTE_BOT_TOKEN=<token de BotFather>
ASISTENTE_CLAVE_CIFRADO=<clave generada>
```

**Hacer el respaldo de la clave ahora**, fuera del PC (gestor de contraseñas o papel). Si se pierde,
las claves de Gemini no se recuperan: cada usuario tendría que registrar la suya de nuevo. Sin
clave válida el servicio no arranca. Para cambiarla:
`uv run --group asistente buscador.py asistente rotar-clave --nueva <clave nueva>` (genera la
nueva con `generar-clave`; vuelve a cifrar todo sin perder datos), y luego actualizar `.env`.

### 11.3 Tailscale Funnel (URL pública de la API)

La extensión de cada usuario necesita llegar a la API del PC. La API escucha solo en
`127.0.0.1:8787` y se expone con Tailscale Funnel (gratis, sin abrir puertos del router).

```bash
sudo dnf install -y tailscale   # o el instalador de tailscale.com
sudo systemctl enable --now tailscaled
sudo tailscale up
# En la consola de Tailscale (login.tailscale.com): activar HTTPS y Funnel para este equipo.
tailscale funnel --bg 8787
tailscale funnel status          # muestra https://<equipo>.<tailnet>.ts.net
```

Verificar **desde fuera de la red** (por ejemplo, con los datos del celular):

```bash
curl -i https://<equipo>.<tailnet>.ts.net/api/v1/latido   # sin token: debe dar 401
curl -i https://<equipo>.<tailnet>.ts.net/otra-ruta       # fuera de /api/v1/: debe dar 404
```

### 11.4 Configuración (`config.local.yaml`)

Lo propio de este PC va en `config.local.yaml` (no se sube a git y reemplaza lo de `config.yaml`):

```yaml
asistente:
  activo: true
  enlace_canal: false            # solo true tras el piloto y la tienda de Edge
  bot_usuario: "NombreDelBot"    # sin @
  dueno_telegram_id: 123456789
  api:
    url_publica: "https://<equipo>.<tailnet>.ts.net"
  extension:
    url_edge: ""                 # el enlace de la tienda, cuando esté publicada
```

Revisar y aprobar el texto de `asistente.politica` (autorización de datos, versión 1). Si se
cambia el texto, **subir `politica.version`**: todos los usuarios deben aceptarlo de nuevo. El
mismo texto lo sirve la API en `/api/v1/privacidad` como política de privacidad de la tienda.

### 11.5 Servicio

```bash
mkdir -p ~/.config/systemd/user
cp deploy/buscador-asistente.service ~/.config/systemd/user/
# Solo en el piloto desde la copia de desarrollo (~/buscador-asistente):
mkdir -p ~/.config/systemd/user/buscador-asistente.service.d
cp deploy/prueba/buscador-asistente.service.d.conf \
   ~/.config/systemd/user/buscador-asistente.service.d/prueba.conf

systemd-analyze --user verify ~/.config/systemd/user/buscador-asistente.service
systemctl --user daemon-reload
systemctl --user enable --now buscador-asistente.service
journalctl --user -u buscador-asistente -n 50 --no-pager
```

El servicio sale al instante si `activo` es `false`, y avisa si faltan dependencias
(`uv sync --group asistente`). Para comprobar el enlace ⚡ de una vacante sin tocar el canal:
`uv run --group asistente buscador.py asistente enlace computrabajo:<ID>`.

### 11.6 Extensión y selectores

- **Extensión para el piloto:** cargarla descomprimida desde la carpeta `extension/`
  (`edge://extensions` → Modo de desarrollador → *Cargar descomprimida*).
- **Para la tienda de Edge:** `uv run --group asistente buscador.py asistente empaquetar-extension`
  deja `dist/asistente-postulacion-<versión>.zip`. El material de la ficha está en
  `docs/tienda-edge/ficha.md`.
- **Selectores de los portales:** son datos, no código. Viven en `assets/selectores/<portal>.json`
  y la extensión los pide al servidor cuando cambia su `version`. Si un portal cambia su HTML
  (el bot avisa al dueño con evidencia de `formulario_desconocido`): corregir el JSON, **subir
  su `version`**, correr `uv run --group asistente buscador.py asistente selectores recargar` y
  probar con una postulación. No hace falta publicar una versión nueva de la extensión.

### 11.7 Operación, administración, borrado y rollback

| Necesidad | Cómo |
|---|---|
| Estado del servicio | `systemctl --user status buscador-asistente` |
| Log del servicio | `journalctl --user -u buscador-asistente -n 200 --no-pager` |
| Reiniciar tras cambiar la configuración | `systemctl --user restart buscador-asistente` |
| Usuarios y métricas | comandos del dueño en el bot: `/usuarios`, `/stats`, `/plataformas` |
| Suspender o reactivar a alguien | `/suspender ID` y `/reactivar ID`, con el ID que muestra `/usuarios` (quedan en la auditoría) |
| Postulaciones recientes | `sqlite3 data/asistente.db "select id, plataforma, estado, creada from postulaciones order by id desc limit 20"` |
| Resumen diario | incluye usuarios, navegadores en línea, enviadas, respaldo y % de respuestas sin IA |

- **Borrado de datos:** cada usuario se borra a sí mismo con `/borrarme` (perfil, CV, clave,
  historial y vínculos, sin dejar archivos ni filas). Quien sale del grupo queda suspendido, y
  quien no usa el asistente en 12 meses recibe un aviso y luego se borra.
- **Actualizar:** como en la sección 10, y después `systemctl --user restart buscador-asistente`.
- **Rollback del asistente** (el buscador no se toca):

  ```bash
  systemctl --user disable --now buscador-asistente.service
  tailscale funnel reset             # cierra la URL pública
  ```

  Poner `enlace_canal: false` (las fichas del canal vuelven a quedar como antes) y, si se quiere,
  `activo: false`. Los datos de `data/asistente.db` y `data/asistente/` se conservan.
