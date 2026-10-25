## Why

LinkedIn es la fuente con más vacantes del radar (474 de las ~1.080 de los últimos 30 días, según
`docs/asistente/portales.md`), pero un ⚡ en LinkedIn siempre termina en el paquete de respaldo. El
dueño decidió (2026-10-21) automatizar también estas postulaciones, tanto la «Solicitud sencilla»
dentro de LinkedIn como las que llevan a la página de la empresa o a un ATS externo. Antes de
escribir adaptadores hace falta saber **a dónde llevan realmente** esas vacantes. Si la mayoría
termina en dos o tres familias de ATS, conviene un adaptador por familia. Si están muy repartidas,
manda el modo genérico. Este change mide eso con datos reales, igual que se midió el volumen de los
portales antes de conectar elempleo.

## What Changes

- Un comando de solo lectura, `buscador.py asistente medir-linkedin`, que toma una muestra de
  vacantes de LinkedIn de `vacantes.db` y, **sin sesión de LinkedIn** (las mismas páginas públicas
  de invitado que ya usa el radar):
  - distingue «Solicitud sencilla» de solicitud externa;
  - resuelve el enlace de destino de las externas;
  - clasifica el destino por familia: Workday, Greenhouse, Lever, SuccessFactors, Gupy, Teamtailor,
    SmartRecruiters, iCIMS, Taleo, BambooHR, los portales ya conectados (Computrabajo, Magneto,
    elempleo), sitio propio de la empresa o desconocido;
  - abre una sola vez (GET, sin enviar nada) la página de destino y anota si pide iniciar sesión o
    crear una cuenta propia;
  - guarda el resultado en JSON y un resumen en Markdown.
- Los patrones de las familias de ATS, el tamaño de la muestra y la pausa entre peticiones van en
  `config.yaml`.
- El comando respeta el cooldown de LinkedIn que registra el radar, hace pausas entre peticiones y se
  detiene ante un bloqueo (429, 999 o una página de verificación). No evade nada.
- Se documentan en `docs/asistente/portales.md` los resultados de la medición y la **decisión del
  dueño** que revierte el *non-goal* de LinkedIn, con el riesgo registrado: las condiciones de uso de
  LinkedIn (sección 8.2) prohíben bots y extensiones que automaticen acciones, y LinkedIn puede
  restringir la cuenta del dueño y la de los invitados.
- Si las páginas públicas no muestran el tipo de solicitud ni el destino, el respaldo es una muestra
  manual del dueño (unas 30 vacantes, pulsando «Solicitar» él mismo en su sesión) y se documenta igual.
- **Sin cambios** en la extensión, en la cola ni en el comportamiento del ⚡: LinkedIn sigue yendo al
  paquete de respaldo hasta el change siguiente.

## Capabilities

### New Capabilities
- `medicion-destinos-linkedin`: medición de solo lectura del tipo de solicitud y de la página de
  destino de las vacantes de LinkedIn, agrupada por familia de ATS, para priorizar la postulación
  automática.

### Modified Capabilities
(ninguna: el ⚡ de LinkedIn sigue en respaldo hasta el change de postulación)

## Impact

- Código nuevo: `buscador_vacantes/asistente/medicion_linkedin.py` y el subcomando en
  `buscador_vacantes/asistente/cli.py`.
- `config.yaml`: sección `asistente.medicion_linkedin` (muestra, pausa y patrones de ATS).
- Pruebas: `tests/asistente/test_medicion_linkedin.py` con fixtures recortados en
  `tests/fixtures/linkedin/` (sin datos personales).
- Documentación: `docs/asistente/portales.md` (decisión, riesgo y resultados).
- Lectura de `vacantes.db` del Fedora, sin escribir en ella. Peticiones HTTP a LinkedIn (páginas
  públicas) y a los dominios de destino, como máximo una por vacante y por dominio.
- Prepara el change siguiente (postulación en LinkedIn: clasificador de destino, modo genérico por
  bucle, controles ARIA e iframes, permisos opcionales amplios y el flujo de Solicitud sencilla).
