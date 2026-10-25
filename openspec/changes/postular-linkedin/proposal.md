## Why

LinkedIn es la fuente con más vacantes del canal (474 de unas 1.080 en 30 días), pero hoy un ⚡ en LinkedIn
siempre termina en el paquete de respaldo. El dueño revirtió ese *non-goal* el 2026-10-21 y aceptó el
riesgo para su cuenta: quiere postular solo en la **Solicitud sencilla** y en las **solicitudes externas**
(ATS y sitios de empresa), para él y para los invitados, con envío automático también en páginas
desconocidas. La medición (`medir-destinos-linkedin`) y el reconocimiento de los destinos
(`docs/asistente/portales.md`, sección «LinkedIn») mostraron que de las vacantes abiertas, 73 % son externas
y 27 % sencillas, y que las externas se reparten entre Greenhouse, Workday, Ashby, Typeform, Pandapé,
SuccessFactors y sitios propios. Este change monta LinkedIn sobre el motor genérico y autorreparable de
`motor-generico-autorreparable`.

## What Changes

- **LinkedIn como plataforma**: el dominio `linkedin.com` se reconoce y LinkedIn queda en
  `asistente.plataformas.linkedin` (apagada hasta el piloto, y en ensayo después).
- **Aceptación del riesgo por usuario**: antes de postular en LinkedIn, cada usuario acepta de forma expresa
  el riesgo de restricción de su cuenta (sección 8.2 de las condiciones de LinkedIn). Tiene dos
  interruptores propios: «Solicitud sencilla» y «Páginas externas».
- **Resolución del destino con la sesión del usuario**: la extensión abre la vacante en LinkedIn, lee si
  es sencilla, externa (destino en `a[href*="/safety/go"]`), cerrada o pausada, y nunca pulsa «Solicitar»
  en una externa: abre directamente la URL limpia. El destino resuelto se comparte entre usuarios, porque
  no es un dato personal.
- **Clasificador de destino** (con `familia_de` de `medir-destinos-linkedin`): mensajería (WhatsApp,
  correo, Telegram) y ATS con cuenta conocida (Workday, SuccessFactors, Taleo, iCIMS…) van al respaldo sin
  abrir. Las demás pasan al motor genérico, con el adaptador de su familia si existe.
- **Plataforma «externa»** en la extensión, con el **permiso opcional amplio** (`https://*/*`) que el usuario
  concede desde el popup. Páginas prohibidas ampliadas: inicio de sesión, registro, OAuth, pagos y banca.
  Un salto a un dominio no relacionado detiene el flujo.
- **Lectores de esquema de los ATS** (Greenhouse, Ashby, Lever, Typeform): leen el formulario por su API o
  su página pública antes de abrirlo. Así se resuelve todo de antemano y lo que falte se pregunta en la
  card antes de abrir la pestaña. Cada familia trae también su botón y su señal de éxito como datos.
- **Solicitud sencilla**: el motor genérico corre dentro del modal de LinkedIn, con su elección de CV, sus
  preguntas, «Siguiente», «Revisar» y «Enviar solicitud». Además desmarca «Seguir a la empresa». Requiere
  reconocimiento con sesión.
- **Ritmo de LinkedIn**: una postulación a la vez, pausa mínima entre postulaciones de LinkedIn y un tope
  diario por usuario.
- **Pilotos**: ensayo de dos semanas con la cuenta del dueño, luego postulaciones reales del dueño y después
  los invitados.

## Capabilities

### New Capabilities
- `postulacion-linkedin`: aceptación del riesgo e interruptores por usuario, resolución del destino con
  sesión, clasificador de destino, plataforma externa con permiso amplio y páginas prohibidas, Solicitud
  sencilla, ritmo, tope diario y pilotos.
- `esquemas-ats`: lectura del formulario de cada familia de ATS antes de abrirlo (Greenhouse, Ashby, Lever,
  Typeform) y los datos de botón y éxito de cada familia.

### Modified Capabilities
(ninguna en `openspec/specs/`: los requisitos que excluían LinkedIn están en changes sin archivar. Ver
design.md, decisión 1)

## Impact

- **Extensión**: `extension/portales.js` (plataforma `linkedin` y plataforma `externa`, páginas prohibidas,
  saltos de dominio), `extension/manifest.json` (`https://*/*` opcional, versión 1.3.0), `extension/popup.js`
  (pedir el permiso amplio), `extension/servicio.js` (resolución del destino y paso a la página externa) y
  `assets/asistente/selectores/linkedin.json` (vacante, modal de Solicitud sencilla y sesión).
- **Servidor**: `asistente/vacantes.py` (`linkedin.com` → `linkedin`), `asistente/nucleo.py` (camino de
  LinkedIn, interruptores, tope diario), `asistente/api.py` (`POST /postulaciones/{id}/destino`), módulo nuevo
  `asistente/esquemas_ats.py`, tabla nueva `destinos_linkedin`, la conversación de Telegram (aceptación del
  riesgo y `/linkedin`) y la política de datos (versión nueva).
- **Configuración**: `asistente.plataformas.linkedin`, `asistente.linkedin` (`tope_diario`, `pausa_min_s`,
  `familias_con_cuenta`, `mensajeria`) y `asistente.medicion_linkedin.familias` ampliado (Ashby, `grnh.se`,
  Typeform, Pandapé).
- **Dependencias**: requiere `motor-generico-autorreparable` aplicado y la tarea 2.2 de
  `medir-destinos-linkedin` (`familia_de`, `limpiar_destino`).
- **Riesgo**: posible restricción de las cuentas de LinkedIn del dueño y de los invitados, aceptado por el
  dueño y por cada usuario.
