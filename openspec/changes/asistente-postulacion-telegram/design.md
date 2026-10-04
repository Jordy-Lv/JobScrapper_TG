# Design

## Context

- **Publicación en el canal.** El buscador publica con el bot de Hermes, solo con métodos de
  envío. Hermes consulta las actualizaciones de ese bot, así que ningún otro proceso puede
  hacerlo.
- **Formato de los mensajes.** Cada mensaje agrupa varias vacantes (`formato.ficha` y
  `formato.empaquetar`, con un límite de 4096 caracteres). Por eso se usa un **enlace
  profundo** en cada ficha (`https://t.me/<bot>?start=v_<id>`), que abre el bot asistente sin
  callbacks. En la primera visita Telegram muestra "Iniciar"; después entra directo.
- **Vacantes publicadas.** Quedan en `vistas` de `data/vacantes.db` durante 90 días, sin la
  descripción completa. `fuentes_estado` registra los cooldowns.
- **Portales.** Computrabajo y Magneto exigen sesión para postular. Sus formularios no se
  conocen todavía: se reconocen en la tarea 3.1.
- **Gemini.** API REST con `x-goog-api-key`, entrada PDF o imagen en línea y salida JSON con
  esquema. La cuota es por clave y responde 429 al agotarse.
- **Extensiones Manifest V3.** El service worker se suspende; `chrome.alarms` permite alarmas
  periódicas de 30 s como mínimo, y los content scripts corren en las pestañas abiertas. No se
  permite ejecutar código remoto, pero sí recibir datos.
- **Costos.** La tienda de Edge (Microsoft Partner Center) no cobra registro. Tailscale Funnel
  es gratuito en el plan personal.

## Goals / Non-Goals

**Goals:**
- **Un toque**: del ⚡ al resultado sin otra acción del usuario. En los primeros usos se admite
  una pregunta por dato faltante, que no se repite.
- Menos de 2 minutos de punta a punta con el navegador en línea.
- Postulación desde la IP y la sesión del usuario, sin que el servidor guarde sesiones ni
  contraseñas.
- Cero duplicados y cero datos inventados.
- Menos de 2 llamadas de IA por postulación en régimen estable.
- Costo cero.

**Non-Goals:**
- **Postulación automática en LinkedIn** (sus términos la prohíben). elempleo, GetOnBoard y
  los ATS externos usan el paquete de respaldo por ahora.
- **Firefox, Safari y navegadores de celular** (Firefox es viable a futuro con firma gratuita).
- **Postular con el PC del usuario apagado.**
- **Web o panel aparte del bot.**
- **Evadir captchas** o usar técnicas *stealth*.

## Decisions

**1. División: el servidor decide y la extensión ejecuta.**
- `buscador-asistente.service` es un servicio `Type=simple` con `Restart=on-failure`. Un solo
  proceso asyncio corre:
  - el **bot** (`python-telegram-bot` v21, long polling, `ASISTENTE_BOT_TOKEN`);
  - la **API** (FastAPI con uvicorn en `127.0.0.1:8787`, expuesta con Tailscale Funnel);
  - las **tareas periódicas** (indexado, vencimientos, recordatorios, modo automático e
    inactividad).
- **La extensión es delgada**: abre, lee, llena, hace clic y reporta. Todo lo que decide (qué
  responder, qué CV, topes, estados, registro) vive en Python en el servidor.
  - Así casi toda la lógica se prueba con pytest y se corrige sin publicar extensión.
- Alternativa descartada: ejecutor en el servidor con sesiones exportadas. Tenía el riesgo de
  la IP compartida y de sesiones atadas al equipo, y obligaba a guardar sesiones de terceros.

**2. Contrato de la API v1** (todo bajo `/api/v1/`, `Authorization: Bearer <token>`).
- `GET /vincular/<codigo>`: página HTML que la extensión detecta (content script en la URL
  del servidor). La extensión canjea el código con `POST /vincular {codigo}` → `{token}`.
- `POST /latido {version, portales: {computrabajo: bool, magneto: bool}}`: el navegador está
  en línea y el estado de sesión de cada portal. Devuelve `{trabajo?, version_minima,
  selectores_version}`.
- `GET /selectores/<plataforma>`: JSON versionado.
- `POST /postulaciones/<id>/tomar`: asignación atómica a ese navegador.
- `POST /postulaciones/<id>/formulario {campos[]}` → `{respuestas[], cv_url?}` o
  `{esperar_usuario: true}`.
- `GET /postulaciones/<id>/cv`: el PDF del usuario, con un enlace de un solo uso.
- `POST /postulaciones/<id>/paso {paso, detalle}` y
  `POST /postulaciones/<id>/resultado {estado, html_sin_valores?, captura?}`.
- **Seguridad**:
  - tokens de 32 bytes, guardados como SHA-256;
  - límites de frecuencia por token;
  - 512 KB por cuerpo, con la captura opcional comprimida;
  - todo lo que no está bajo `/api/v1/` responde 404.

**3. Extensión (`extension/`, Manifest V3, JavaScript sin compilación).**
- **Permisos**: `storage`, `tabs`, `alarms` y `scripting`, más `host_permissions` solo para
  `*.computrabajo.com`, `*.magneto365.com` y la URL del servidor. Sin `cookies` ni
  `<all_urls>`.
- **Service worker**: una alarma cada 30 s envía el latido. Si hay trabajo, abre una pestaña
  en segundo plano (`active: false`) e inyecta el adaptador del portal.
- **Adaptadores** (`adaptadores/computrabajo.js` y `magneto.js`) sobre un motor común
  (`motor.js`):
  - pasos declarativos: esperar elemento, clic, leer campos, llenar, adjuntar, enviar y
    esperar confirmación;
  - los selectores vienen del JSON del servidor;
  - el código no cambia con los selectores, solo con flujos nuevos.
- **Llenado**:
  - eventos nativos (`input`, `change`) para que el portal registre los valores;
  - pausas cortas entre campos;
  - el archivo se adjunta con `DataTransfer`, creando el `File` desde el PDF descargado del
    servidor.
- **Detección de sesión y de cuenta**: el adaptador comprueba un indicador de usuario con
  sesión iniciada en la página y lee el correo de la cuenta desde la página de perfil o de
  cuenta del portal (selector `cuenta.correo`). El correo se cachea en `chrome.storage` y se
  relee antes de cada trabajo. No lee cookies.
- **Captcha**: si aparece un elemento de desafío conocido (iframes de reCAPTCHA o hCaptcha, o
  textos de verificación), la pestaña se activa y se mantiene abierta. La extensión sondea cada
  10 s si el desafío desapareció para continuar, durante 2 h como máximo.
- **Popup**:
  - estado (vinculado, en línea, portales listos);
  - última postulación;
  - botones "Vincular con código" y "Pausar".
- **Navegador cerrado a mitad**: el servidor detecta que el latido se cortó con la
  postulación `tomada` y decide según `envio_pulsado`. La extensión reporta `envio_pulsado`
  antes de pulsar el envío y espera la confirmación del servidor.
- Alternativa descartada: TypeScript con bundler. Agrega una cadena de compilación por unos
  cientos de líneas.

**4. Distribución gratuita.**
- **Edge**: publicación en la tienda de complementos de Microsoft con una cuenta individual
  gratuita de Partner Center. Visibilidad oculta si la opción está disponible; si no, pública.
  Actualizaciones automáticas.
- **Chrome y Brave**: el bot entrega el `.zip` de la última versión con una guía de carga
  descomprimida. `version_minima` en el latido obliga a actualizar cuando un cambio de flujo lo
  exige, y el bot avisa.
- Se descartó la Chrome Web Store (5 USD).
- Se descartó el `.crx` autoalojado: Chrome lo bloquea fuera de la tienda.

**5. Base propia `data/asistente.db` y lectura de solo lectura de `vacantes.db`.**
- `vacantes.db` se abre con `file:…?mode=ro`.
- **Tablas:**
  - usuarios y acceso: `usuarios` (con `miembro_verificado_en`), `navegadores` (hash del
    token, nombre, versión, `ultimo_latido`, estado de cada portal: `sin_sesion`, `incompleto`
    o `listo`);
  - vacantes: `vacantes` (índice `id_corto` y caché de detalle y requisitos);
  - postulaciones: `postulaciones` (`usuario_id`, `id_corto`, `estado`, `navegador_id`,
    `envio_pulsado`, `cv_archivo`, fechas; `UNIQUE(usuario_id, id_corto)`),
    `postulacion_pasos`, `respuestas` (campo, respuesta, origen);
  - respuestas: `banco_preguntas`, `respuestas_aprendidas`, `pendientes_usuario` (preguntas en
    espera);
  - control: `selectores` (plataforma, versión, JSON), `ia_uso`, `auditoria`, `bajas`.
- Los archivos se guardan con nombres aleatorios en `data/asistente/usuarios/<uuid>/`, con
  permisos 700.

**6. Estados de la postulación.**
- `en_cola`:
  - pasa a `tomada` cuando un navegador la asigna;
  - pasa a `esperando_navegador` si no hay latido en 2 min;
  - pasa a `respaldo` a las 24 h sin navegador.
- `tomada` → `en_curso`, que termina en uno de estos:
  - `enviada`
  - `ya_postulada`
  - `vacante_cerrada`
  - `esperando_usuario`, que vuelve a `en_cola` al responder o pasa a `respaldo` a las 12 h
  - `esperando_sesion`, que vuelve a `en_cola` al detectar la sesión o pasa a `respaldo` a las 24 h
  - `verificacion` (captcha visible al usuario), que vuelve a `en_curso` o pasa a `bloqueada` a las 2 h
  - `cuenta_distinta`, que vuelve a `en_cola` si el usuario acepta la cuenta nueva o inicia sesión con la suya
  - `formulario_desconocido`
  - `incierta`
  - `fallida`
- **Si se corta el latido de un navegador con una postulación tomada**:
  - sin `envio_pulsado` → vuelve a `en_cola`;
  - con `envio_pulsado` → `incierta`.
- Cada transición es condicional y se registra en `postulacion_pasos`.

**7. Selectores como datos versionados.**
- `assets/selectores/<plataforma>.json` es el origen. Se cargan a la tabla `selectores` al
  arrancar o con `asistente selectores recargar`, e incluyen:
  - selectores CSS y alternativos por elemento;
  - textos de referencia normalizados (confirmación, ya postulado, cerrada, sesión iniciada);
  - tiempos de espera.
- La extensión los pide cuando cambia `selectores_version` y nunca ejecuta código remoto.

**8. Acceso solo para miembros del grupo.**
- El bot asistente se agrega al grupo privado de las vacantes como **administrador sin
  permisos**. Telegram solo permite consultar la membresía de otros con `getChatMember` si el
  bot es administrador.
- Se consideran miembros los estados `member`, `administrator`, `creator` y `restricted` con
  `is_member`. Los estados `left` y `kicked` no lo son.
- **Cuándo se comprueba:**
  - al iniciar el alta, antes de guardar cualquier dato;
  - en cada ⚡, con caché de 10 min;
  - una vez al día para todos los usuarios, en una tarea periódica.
- Si la consulta falla por permisos, se bloquean las altas, se conserva el estado de los
  usuarios y se avisa al dueño.
- El grupo es el mismo `TELEGRAM_CHAT_ID` del buscador (`-1004429829042`, confirmado por el
  dueño, que es administrador del chat), salvo que `asistente.grupo.chat_id` diga otro.
- Alternativa descartada: códigos de invitación. El dueño ya controla quién entra al grupo, así
  que duplicar ese control solo agrega fricción.

**9. Completado del perfil del portal.**
- El latido informa por portal `sin_sesion`, `incompleto` o `listo`. Lo determina el
  adaptador revisando las secciones del perfil indicadas en los selectores: hoja de vida
  cargada, datos personales, formación y experiencia.
- Con `incompleto`, el servidor encola un trabajo de tipo `completar_perfil`, que tiene
  prioridad sobre las postulaciones de ese portal y usa el mismo motor, ritmo, registro y
  evidencia.
- Los selectores del perfil incluyen solo las secciones permitidas. Las páginas de contraseña,
  correo de acceso, privacidad y notificaciones nunca se tocan, y el motor solo agrega o llena
  vacíos: nunca borra.
- **Sin cuenta**: el bot envía el enlace de registro del portal (`selectores.<x>.url_registro`)
  y la guía. La cuenta no se crea automáticamente porque exige la contraseña, la verificación
  del correo y la aceptación de los términos por el propio usuario.

**9a. Cuenta del portal asociada.**
- La tabla `cuentas_portal` guarda `usuario_id`, `plataforma`, `correo_cifrado` (Fernet),
  `correo_hash` (SHA-256 del correo normalizado en minúsculas) y `confirmada_en`.
- **Latido**: envía por portal `{estado, correo}`. El servidor compara el hash y responde si
  hay coincidencia. La extensión no ejecuta un trabajo sin `cuenta_ok`.
- **Primera detección**: el bot pide confirmar el correo con botones.
- **Cuenta distinta**: el trabajo pasa a `cuenta_distinta` y se avisa con el correo encontrado
  enmascarado (primera letra, `***` y el dominio). El correo ajeno no se guarda.
- Si `cuenta.correo` no se encuentra en la página, el resultado es `formulario_desconocido`.
  Nunca se postula sin verificar.
- `/estado` y `/perfil` muestran el correo asociado por plataforma, descifrado al momento.
- Alternativa descartada: solo un hash, sin el correo visible. El dueño pidió ver el correo de
  cada plataforma, y el usuario necesita reconocer la cuenta para confirmarla.

**9b. CV del portal por vacante.**
- Los selectores de cada portal declaran `cv.modo`:
  - `adjunto`: el formulario de postulación acepta un archivo;
  - `perfil_unico`: un solo CV en el perfil, que se reemplaza;
  - `perfil_multiple`: varios CV, con un límite; se sube y se selecciona.
- Antes de `enviar`, si el modo no es `adjunto` y `usuarios.actualizar_cv_portal` es verdadero, el motor ejecuta los pasos `cv_subir` y `cv_verificar` (el nombre del archivo nuevo aparece en el perfil).
- **En `perfil_multiple`**, los archivos que sube el sistema se identifican por su nombre fijo `CV_<Nombre>_<Apellido>.pdf`. Al alcanzar el límite, solo se reemplazan esos.
- **En `perfil_unico`**, el primer reemplazo de un CV que no subió el sistema exige la autorización explícita del alta.
- **Si `cv_verificar` falla**, se continúa con el CV existente y se registra.
- La tarea 3.1 documenta si el empleador ve el CV del momento de la postulación o el actual del perfil. Con la adaptación leve, el riesgo de incoherencia es bajo y queda informado en la autorización.

**10. Id corto del enlace.**
- Los primeros 12 caracteres base32 en minúscula de `sha256(clave)`.
- `formato.ficha` usa `asistente/enlaces.py`, un módulo puro.
- El asistente indexa las `vistas` enviadas al arrancar, cada 5 min y ante un id desconocido
  (una sola vez).

**11. Gemini por REST con un cliente async propio.**
- **Tareas**: `leer_cv`, `requisitos`, `adaptar_cv`, `carta`, `responder` y
  `clasificar_pregunta`. Cada una tiene su modelo y su esquema pydantic, exportado a
  `responseSchema`.
- **Validación de la clave**: con `GET /models`.
- **429 con `retryDelay`**: si es de 20 s o menos, se reintenta; si no, `CuotaAgotada`.
- **Contenido externo**: va entre delimitadores, con una instrucción fija que manda ignorar las
  instrucciones que contenga.
- **Sin IA**: la postulación sigue con el CV base, la cascada sin IA y las preguntas abiertas
  al usuario.
- Se descartó el SDK oficial (más dependencias y cambios frecuentes).

**12. Cifrado.**
- Fernet (`cryptography`) con `ASISTENTE_CLAVE_CIFRADO` para las claves de Gemini.
- `asistente generar-clave` y `asistente rotar-clave`.
- Si la clave maestra falta o es inválida, el servicio no arranca. Su respaldo está documentado.

**13. Lectura del CV.**
- `pypdf` local, con límites de 10 páginas y 5 MB y un tiempo máximo.
- Antes de enviar, se enmascaran el correo, el teléfono, el documento y la dirección.
- Un PDF escaneado pide confirmación para enviar el archivo.
- La salida es un `PerfilExtraido` que se confirma por secciones con botones.

**14. Banco compartido y catálogo de campos.**
- **Catálogo cerrado** (`asistente/campos.py`):
  - campos simples: `nombre`, `correo`, `telefono`, `documento`, `salario`,
    `disponibilidad_inicio`, `horario`, `modalidades`, `ciudad`, `traslado`,
    `estudia_actualmente`, `institucion`, `programa`, `semestre`, `tipo_practica`,
    `ingles_nivel`, `equipo_propio`, `experiencia_meses`, `enlace_portafolio`;
  - campos con parámetro: `conoce:<habilidad>` e `idioma:<idioma>`.
- **Banco**: sembrado con unas 60 preguntas en `assets/banco_preguntas.yaml`.
- **Pregunta nueva**: se clasifica una sola vez y queda para todos.
- **Opciones**: se comparan con equivalencias normalizadas.
- **Campos estándar** (nombre, correo, teléfono, archivo): los identifica el servidor por la
  etiqueta, el `name` y el tipo que envía la extensión, sin IA.

**15. CV: adaptación leve validada.**
- `adaptar_cv` devuelve solo `{resumen, habilidades_primero[≤6], reemplazos[≤3]}`.
- **Validador**:
  - las habilidades deben estar en el perfil;
  - cada reemplazo debe estar en la tabla de sinónimos;
  - el resumen no puede mencionar tecnologías ausentes del perfil.
  - Si algo falla, se usa la parte correspondiente del CV base.
- **PDF**: `fpdf2`, plantilla ATS de una columna y sin foto, Noto Sans (licencia OFL), como
  máximo 2 páginas y nombre fijo `CV_<Nombre>_<Apellido>.pdf`.

**16. Detalle de la vacante y afinidad.**
- **Extractores por fuente** y uno genérico.
- **Ritmo**: un request cada 5 s por dominio como mínimo; se respetan los cooldowns.
- **Caché**: 24 h, compartida.
- **Requisitos**: se extraen una vez por vacante.
- **Afinidad determinista**: informativa; solo decide en el modo automático por usuario.

**17. Configuración.**
```yaml
asistente:
  activo: false
  enlace_canal: false
  bot_usuario: ""
  dueno_telegram_id: 0
  api: {host: 127.0.0.1, puerto: 8787, url_publica: ""}
  extension: {url_edge: "", version_minima: "1.0.0", latido_s: 30, navegador_caido_min: 2}
  grupo: {chat_id: "", comprobar_cada_h: 24}   # grupo privado de las vacantes
  politica: {version: 1, texto: |- ...}
  cv: {max_mb: 5, max_paginas: 10}
  topes: {usuario_dia: 15, ia_usuario_dia: 60, mensajes_min: 30}
  ejecucion:
    pausa_s: {min: 45, max: 120}
    espera_navegador_h: 24
    espera_usuario_h: 12
    espera_sesion_h: 24
    espera_verificacion_h: 2
  plataformas: {computrabajo: {automatica: true}, magneto: {automatica: true}}
  automatico_usuario: {umbral_defecto: 70}
  carta_max_caracteres: 1000
  recordatorio_dias: 2
  inactividad_meses: 12
  retencion_dias: 90
  evidencia_dias: 30
  detalle: {intervalo_dominio_s: 5, timeout_s: 15, cache_h: 24}
  preguntas_tipicas: {computrabajo: [...], magneto: [...], otras: [...]}
  gemini:
    base_url: https://generativelanguage.googleapis.com/v1beta
    tareas: {leer_cv: {...}, requisitos: {...}, adaptar_cv: {...}, carta: {...},
             responder: {...}, clasificar_pregunta: {...}}
```

**18. Dependencias y pruebas.**
- **Grupo `asistente`**: `python-telegram-bot>=21`, `fastapi`, `uvicorn`, `cryptography`,
  `pypdf` y `fpdf2`.
- **En desarrollo**: `playwright`, para cargar la extensión en Chromium
  (`launch_persistent_context` con `--load-extension`) y ejecutarla sobre fixtures HTML
  servidos con `page.route`, contra una API de prueba. Esas pruebas se marcan `navegador` y se
  saltan si no hay Chromium.
- El buscador solo importa `asistente/enlaces.py`.

## Análisis de casos

| Caso | Comportamiento |
|---|---|
| Toque ⚡ con el navegador en línea y el portal listo (caso normal) | "Postulando…" → progreso en el mismo mensaje → "✅ Enviada" con las preguntas y respuestas. Ninguna otra acción. |
| Toque desde el celular con el PC apagado | "Se enviará cuando abras tu navegador"; se ejecuta sola al volver el latido; a las 24 h, paquete de respaldo. |
| Miembro del grupo no registrado toca ⚡ | Se comprueba la membresía; alta (autorización, clave, CV, cuestionario, vincular navegador); al terminar se procesa esa vacante. |
| No miembro escribe al bot (o le reenvían un ⚡) | "El asistente es exclusivo del grupo"; no se guarda nada. |
| Usuario sale o es expulsado del grupo | Suspendido en la siguiente comprobación; sus pendientes se cancelan. Se reactiva si vuelve. |
| El bot pierde el rol de administrador del grupo | Altas bloqueadas, usuarios existentes intactos y aviso al dueño. |
| Otra persona inició sesión en el portal en tu navegador | `cuenta_distinta`: no se postula; el bot te muestra tu correo asociado y el encontrado enmascarado, con "Es mi cuenta nueva" o "No es mía". |
| Usuario sin cuenta en el portal | El bot indica que falta crearla, con el enlace de registro y la guía; al detectar la sesión avisa "listo". La vacante espera 24 h y luego va al paquete. |
| Perfil del portal incompleto (sin hoja de vida, sin formación) | Trabajo `completar_perfil` automático con el perfil y el CV base, con prioridad; luego la postulación sigue. |
| Sin navegador vinculado | Paquete de respaldo con el paso a paso para instalar y vincular. |
| Sesión del portal no iniciada | `esperando_sesion` y un aviso "Inicia sesión en Computrabajo en Edge"; se retoma sola al detectarla. |
| Plataforma no soportada | Paquete de respaldo con el motivo. |
| Pregunta obligatoria sin dato | Pestaña cerrada sin enviar; el bot pregunta (botones o texto), lo guarda y la postulación se reencola sola. |
| Captcha o verificación | La pestaña se muestra; "Completa la verificación en tu navegador"; la extensión continúa al resolverse; a las 2 h, `bloqueada` y respaldo. |
| Formulario cambiado | `formulario_desconocido`; HTML sin valores al servidor; aviso al dueño; paquete al usuario. El dueño corrige el selector y la siguiente funciona sin publicar extensión. |
| Navegador cerrado antes de enviar | Vuelve a la cola. |
| Navegador cerrado después de pulsar enviar | `incierta`; se pide verificar en "Mis postulaciones". |
| Confirmación ausente | `incierta`, sin reintento. |
| Ya postulado antes (a mano) | `ya_postulada`. |
| Vacante cerrada | `vacante_cerrada`. |
| Doble toque o dos navegadores del mismo usuario | `UNIQUE` y `tomar` atómico: una sola ejecución. |
| Tope diario alcanzado | Queda para el día siguiente, con aviso. |
| Sin clave de Gemini o cuota agotada | Postula igual con el CV base y la cascada sin IA; lo abierto se le pregunta al usuario. |
| La IA inventa en el resumen | El validador usa el resumen base. |
| Instrucciones incrustadas en el CV o la vacante | Se tratan como datos, con esquema JSON y validadores. |
| Formulario sin campo de archivo (usa el CV del perfil) | Con autorización: se reemplaza o sube el CV adaptado, se verifica y se postula. Sin autorización o si falla: se postula con el CV existente y se registra. |
| Extensión manual desactualizada | `version_minima` la frena y el bot guía la actualización. |
| Token de extensión robado | Solo permite ver la cola y reportar de ese usuario; se revoca con `/navegadores`. No hay contraseñas ni sesiones que robar. |
| Usuario bloquea al bot | Usuario inactivo; no se encola nada en modo automático. |
| `/borrarme` | Borra perfil, CV, clave, navegadores, historial y evidencia. |
| Servidor o Tailscale caídos | La extensión reintenta el latido con espera creciente; nada se pierde; el buscador sigue publicando. |
| Clave maestra perdida | Las claves de Gemini no se recuperan; cada usuario la registra de nuevo. Hay que respaldarla. |

## Risks / Trade-offs

- **[Los portales cambian el HTML]** → Selectores como datos en el servidor (se corrigen sin
  publicar), detección con evidencia y aviso al dueño.
- **[Términos de uso de los portales]** → Ritmo humano, tope diario, el navegador real del
  usuario y detención ante verificaciones. Cada usuario acepta el riesgo.
- **[El PC del usuario apagado]** → Cola con espera de 24 h y aviso, y paquete de respaldo.
- **[Revisión o rechazo en la tienda de Edge]** → Propósito único declarado, política de
  privacidad y permisos mínimos. Mientras tanto, la carga manual funciona en Edge, Chrome y
  Brave.
- **[MV3 suspende el service worker]** → Alarma de 30 s y estado en `chrome.storage`; una
  postulación en curso vive en el content script de su pestaña.
- **[Datos de terceros en tu PC]** → Sin sesiones ni contraseñas; claves cifradas, permisos
  700/600, borrado a pedido y por inactividad, auditoría y logs sin datos personales.
- **[Límites gratuitos de Gemini cambiantes]** → Modelos por tarea en la configuración y
  degradación sin IA.

## Migration Plan

1. **Servidor.**
   - `uv sync --group asistente`.
   - Crear el bot en BotFather.
   - `asistente generar-clave` (y respaldarla).
   - Instalar Tailscale y ejecutar `tailscale funnel --bg 8787`.
   - Completar `asistente.*`.
2. **Reconocimiento de los portales** (tarea 3.1) con la cuenta del dueño en su navegador.
3. **Piloto privado** con `enlace_canal: false` y la extensión cargada descomprimida en el Edge
   del dueño.
4. **Piloto con 2 o 3 invitados** durante 3 días como mínimo.
5. **Publicación en la tienda de Edge** y `enlace_canal: true`.

**Rollback:**
- `enlace_canal: false` quita los ⚡.
- `plataformas.<x>.automatica: false` deja esa plataforma en modo paquete.
- Detener el servicio apaga todo, sin afectar al buscador.

## Open Questions

- El flujo exacto de cada portal, incluidas sus páginas de perfil (tarea 3.1).
- Los modelos gratuitos vigentes de Gemini (tarea 4.1).
- Si la tienda de Edge ofrece visibilidad oculta para cuentas individuales (tarea 9.5).
- El texto final de la autorización (tarea 2.2).
