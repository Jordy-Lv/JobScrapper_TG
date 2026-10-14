## Why

Tras la fase 1, el código está en `comun/`, `radar/` y `asistente/`, pero `assets/` y `docs/` siguen planos y mezclados: en `assets/` conviven el logo de marca, el encabezado del radar, las fuentes del PDF del asistente y los selectores de los portales; en `docs/` conviven la especificación del radar, la guía del asistente y las notas históricas de Hermes. Ordenarlos con la misma lógica (marca / radar / asistente) hace que cada recurso diga a qué parte pertenece y deja un lugar para registrar decisiones de arquitectura. Es la fase 2 del plan de reestructura y no cambia lo que hace el sistema.

## What Changes

- Reorganizar `assets/` con `git mv`:
  - `assets/marca/`: `logo.jpg`, `logo_emblema.png`, `welcome_banner.jpg`.
  - `assets/radar/`: `encabezado_vacantes.jpg` y `certs/` (certificado intermedio del SPE).
  - `assets/asistente/`: `banco_preguntas.yaml`, `tecnologias.yaml`, `selectores/` y `fuentes/` (tipografías del PDF).
- Reorganizar `docs/` con `git mv`:
  - `docs/radar/`: `buscador-vacantes-spec.md` y `diagnostico-practicas-falsos-positivos.md`.
  - `docs/asistente/`: `guia-usuario.md`, `guia-asistente-postulacion.pdf` y `tienda-edge/`.
  - `docs/referencia/`: `referencia_hermes/` (material histórico).
  - `docs/decisiones/`: nuevo ADR `0001-paquetes-comun-radar-asistente.md` que registra la arquitectura de la fase 1 y la regla `comun ← asistente ← radar`.
- Actualizar las rutas que apuntan a lo movido: constantes en el código (`respuestas`, `tecnologias`, `nucleo`, `cv_pdf`, `spe`), el valor por defecto de `banner.imagen` en `config.py` y en `config.yaml`, pruebas, `README.md`, `deploy/INSTALAR.md`, comentarios de la extensión, `openspec/config.yaml` y las referencias a `docs/` en `CLAUDE.md`.
- Borrar `assets/logo_v1.jpg` y `assets/logo_v2.jpg` (no los referencia nada), **solo tras confirmación expresa del dueño**.
- **Sin** cambios de comportamiento, de esquemas ni de mensajes. `config.yaml` solo cambia el valor de una ruta (`banner.imagen`).

## Capabilities

### New Capabilities
- `organizacion-recursos`: estructura de `assets/` y `docs/` por pertenencia (marca, radar, asistente, referencia, decisiones) y regla de que toda ruta a un recurso se resuelva en un solo lugar.

### Modified Capabilities

## Impact

- Código: 6 constantes de ruta (`asistente/respuestas.py`, `asistente/tecnologias.py`, `asistente/nucleo.py`, `asistente/cv_pdf.py`, `radar/fuentes/spe.py`, `comun/config.py`) y `config.yaml` (una línea).
- Pruebas: `tests/radar/test_publicacion.py` y `tests/asistente/test_extension.py` citan rutas de `assets/`; el resto las toma de las constantes.
- Documentos y archivos de instrucciones: `README.md` (logo y árbol), `deploy/INSTALAR.md`, `CLAUDE.md` y `openspec/config.yaml` (ruta de `buscador-vacantes-spec.md`); los planes de changes abiertos que citen estas rutas.
- Despliegue: ningún servicio cambia de comando; el `git pull` basta. Hay que reiniciar `buscador-asistente` para que cargue las rutas nuevas, y el radar las toma en su próxima corrida.
- La extensión empaquetada no incluye `assets/`, pero sus comentarios citan `assets/selectores/`.
- Precondición: ninguna pendiente (fase 1 en `main` y desplegada).
