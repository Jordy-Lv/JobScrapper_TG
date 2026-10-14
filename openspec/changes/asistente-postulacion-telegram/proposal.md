## Why

El canal publica vacantes de prácticas, aprendiz y junior TI a diario, pero cada miembro tiene
que postular a mano:
- abrir el portal;
- llenar el formulario;
- responder las mismas preguntas filtro;
- adjuntar el CV.

En las prácticas gana quien postula primero.

El objetivo es que un usuario (más de 5, cada uno con su cuenta) **solo toque ⚡ Postularme** en
una vacante del canal y el sistema haga todo lo demás:
- llenar los datos;
- responder las preguntas con su perfil;
- adjuntar un CV levemente adaptado a esa oferta;
- enviar la postulación desde su propio navegador e IP;
- confirmarle el resultado con el detalle de lo que respondió.

Todo sin costo: el servidor es el PC Fedora, la IA es la clave gratuita de Gemini de cada
usuario y la extensión se distribuye gratis.

## What Changes

- **Enlace ⚡ Postularme en cada ficha del canal.** Abre el bot asistente sobre esa vacante, y
  ese toque **es la orden de postular**: no hay más confirmaciones.
- **Servidor en el PC Fedora: el cerebro.**
  - **Bot multiusuario** propio, distinto del de Hermes.
  - **Usuarios**: alta guiada con autorización de datos (Ley 1581), acceso solo para miembros del grupo privado (comprobado con Telegram),
    clave de Gemini cifrada, CV leído por Gemini, cuestionario base, perfil y enfoque.
  - **Preparación**: resolución de respuestas, CV adaptado en PDF y afinidad.
  - **Gestión**: cola y reglas, selectores de los portales, registro y evidencia, avisos y
    administración.
  - **API mínima para la extensión**, publicada gratis con **Tailscale Funnel**, sin dominio.
- **Extensión de navegador: las manos.**
  - Edge es el navegador principal, desde la tienda de complementos de Microsoft (registro
    gratuito y actualizaciones automáticas). Chrome y Brave quedan por carga manual.
  - Se vincula con un toque desde el bot.
  - Detecta si el usuario tiene sesión en Computrabajo y Magneto.
  - Ejecuta en segundo plano, en el navegador del usuario, las postulaciones de su cola.
  - Lee el formulario, pide las respuestas al servidor, llena todo, adjunta el CV, envía,
    confirma y reporta cada paso.
  - Los selectores llegan del servidor como datos, así que un cambio de página se corrige sin
    publicar una versión nueva.
  - **El servidor nunca recibe contraseñas ni sesiones.**
- **Respuestas en cascada con mínimo uso de IA.** El orden es:
  1. perfil;
  2. banco compartido de preguntas;
  3. respuestas aprendidas;
  4. Gemini.

  Si un dato obligatorio no existe, el bot lo pregunta **una sola vez** con botones, la
  postulación sigue sola y la respuesta queda guardada.
- **CV con adaptación leve.**
  - Lo que se ajusta: el resumen, el orden de hasta 6 habilidades y hasta 3 términos
    equivalentes de la oferta.
  - Lo que no cambia: la estructura, las experiencias y los proyectos.
  - Un validador garantiza que no se inventa nada.
- **Cuando no se puede automatizar**, el usuario recibe un **paquete listo para copiar**
  (respuestas, carta, CV adaptado y enlace) con el motivo y cómo hacerlo automático. Pasa con:
  - portales no soportados (LinkedIn, elempleo, GetOnBoard y otros);
  - usuarios sin navegador vinculado;
  - un navegador que no se conecta en 24 h.
- **Seguridad.**
  - Ante un captcha, la extensión se detiene y le pide al usuario completarlo él mismo en su
    navegador; nunca lo evade.
  - Ante un formulario desconocido o una confirmación ausente, se detiene y reporta.
  - Nunca postula dos veces a la misma vacante.
- **Resumen diario**: suma métricas agregadas del asistente.

## Capabilities

### New Capabilities
- `usuarios-asistente`: alta, autorización, acceso solo para miembros del grupo privado (comprobado con Telegram), perfil desde el CV,
  cuestionario base, edición, baja con borrado total y administración.
- `ia-usuario-gemini`: clave de Gemini por usuario, usos permitidos, topes, cuota agotada,
  datos que nunca se envían y defensa ante instrucciones incrustadas.
- `extension-navegador`: instalación sin costo, vinculación por enlace, detección de sesión,
  ejecución de la cola en el navegador del usuario, selectores entregados por el servidor y
  reporte de errores con evidencia.
- `postulacion-automatica`: orden por ⚡, preparación en el servidor, postulación completa,
  datos faltantes, ritmo y topes, captcha resuelto por el usuario, detención segura, unicidad,
  registro detallado y modo automático por usuario.
- `paquete-postulacion`: resolución del enlace, detalle de la vacante, afinidad, cascada de
  respuestas con banco compartido, paquete de respaldo, seguimiento y bot robusto.
- `cv-adaptado`: adaptación leve del CV a cada oferta sin inventar datos y PDF apto para ATS.

### Modified Capabilities
- `publicacion-telegram`: cada ficha incluye el enlace ⚡ Postularme cuando está habilitado.
- `resumen-diario`: incluye las métricas agregadas del asistente.

## Impact

- **Código nuevo**:
  - paquete `buscador_vacantes/asistente/`: bot, usuarios, perfil, Gemini, banco, detalle,
    CV, cola, API, selectores y registro;
  - extensión `extension/` (Manifest V3, JavaScript sin compilación);
  - subcomandos `asistente …`.
- **Código modificado**: `formato.py` (enlace ⚡), `config.py` y `config.yaml` (sección
  `asistente`) y `resumen.py`.
- **Datos**: base propia `data/asistente.db`, con lectura de solo lectura de `vacantes.db`.
  Los archivos por usuario van en `data/asistente/usuarios/<uuid>/` con permisos 700.
- **Dependencias** en el grupo opcional `asistente`: `python-telegram-bot`, `fastapi`,
  `uvicorn`, `cryptography`, `pypdf` y `fpdf2`. `playwright` queda solo en desarrollo, para
  probar la extensión.
- **Secretos nuevos**: `ASISTENTE_BOT_TOKEN` y `ASISTENTE_CLAVE_CIFRADO`.
- **Despliegue**: `deploy/buscador-asistente.service`, Tailscale Funnel (plan personal
  gratuito), cuenta de desarrollador gratuita en Microsoft Partner Center y publicación en la
  tienda de Edge.
- **Riesgos aceptados**:
  - Los términos de uso de los portales pueden restringir la automatización; cada usuario lo
    acepta en la autorización.
  - La postulación automática necesita el PC del usuario encendido con el navegador abierto:
    si no, espera en cola y, pasadas 24 h, se entrega el paquete.
- **Regla del proyecto que se amplía**: Gemini (de cada usuario) lee CV y redacta respuestas,
  y una extensión en el navegador del usuario postula por él. Las protecciones anti-bot siguen
  sin evadirse y DeepSeek mantiene su rol.
