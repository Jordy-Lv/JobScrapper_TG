# Tasks

## 1. Base: dependencias, configuración, datos y cifrado

- [x] 1.1 Agregar a `pyproject.toml` el grupo `asistente` (`python-telegram-bot>=21`, `fastapi`, `uvicorn`, `cryptography`, `pypdf`, `fpdf2`) y `playwright` al grupo `dev`, y actualizar `uv.lock`. Verificar:
  - `uv sync` sin el grupo deja `uv run pytest` en verde;
  - `uv sync --group asistente` instala sin error.
- [x] 1.2 Crear la sección `asistente` en `config.py` (pydantic) y en `config.yaml` (valores del design 17, desactivada y con `enlace_canal: false`), y agregar `ASISTENTE_BOT_TOKEN` y `ASISTENTE_CLAVE_CIFRADO` a `Secretos` y `.env.example`. Verificar con `tests/test_config.py` que:
  - la configuración por defecto carga;
  - un modo de registro inválido, topes negativos o una tarea de Gemini sin modelo se rechazan indicando el campo.
- [x] 1.3 Crear `buscador_vacantes/asistente/datos.py` con el esquema de `data/asistente.db` (design 5) en WAL, más `abrir_vacantes_ro()`. Verificar con `tests/test_asistente_datos.py` que:
  - las tablas se crean;
  - `vacantes.db` no se puede escribir desde esa conexión;
  - `UNIQUE(usuario_id, id_corto)` se respeta.
- [x] 1.4 Crear `asistente/cifrado.py` (Fernet) y los subcomandos `asistente generar-clave` y `asistente rotar-clave`. Verificar con pruebas de cifrado y descifrado ida y vuelta, de clave inválida (el servicio no arranca) y de rotación sin pérdida.

## 2. Enlaces del canal y usuarios

- [x] 2.1 Crear `asistente/enlaces.py` (`id_corto`, `enlace`) y hacer que `formato.ficha` agregue `⚡ Postularme` solo con `activo` y `enlace_canal` habilitados, contando la longitud en `empaquetar`. Verificar con `tests/test_formato.py` que:
  - el id es estable y de 12 caracteres;
  - con el enlace deshabilitado, las fichas quedan idénticas a las actuales;
  - con el enlace habilitado se respetan los 4096 caracteres.
- [ ] 2.2 Redactar el texto de la autorización y política de datos en `asistente.politica`, versión 1. Debe cubrir:
  - finalidad y datos;
  - Gemini con la clave del usuario y el uso de datos del plan gratuito;
  - la extensión que postula desde su navegador, sin enviar contraseñas ni sesiones;
  - la actualización de su hoja de vida en los portales con la versión adaptada a cada vacante, y que un empleador anterior podría ver la versión más reciente;
  - el riesgo de restricción de cuentas;
  - derechos y borrado.

  El mismo texto sirve de política de privacidad para la tienda de Edge. Verificar que el dueño lo aprueba antes de 9.3.
- [x] 2.3 Crear `asistente/usuarios.py`:
  - alta con `paso_alta` persistente;
  - aceptación versionada;
  - comprobación de membresía en el grupo con `getChatMember` (alta, cada ⚡ con caché de 10 min y tarea diaria), con suspensión al salir y reactivación al volver;
  - bloqueo de altas y aviso al dueño si falla por permisos;
  - suspensión, inactividad y borrado total;
  - auditoría.

  Verificar con `tests/test_asistente_usuarios.py` (respx sobre la Bot API):
  - un no miembro es rechazado sin guardar datos;
  - `left` y `kicked` suspenden y cancelan pendientes;
  - volver al grupo reactiva;
  - un error de permisos bloquea altas sin tocar a los existentes;
  - nueva versión de la política;
  - el borrado no deja archivos ni filas del usuario;
  - inactividad con aviso y borrado.

## 3. Reconocimiento de los portales

- [ ] 3.1 En el navegador del dueño, con su sesión, recorrer en Computrabajo y en Magneto al menos 3 vacantes reales hasta el formulario **sin enviar**, guardando el HTML de cada paso (Guardar página en DevTools). Registrar:
  - los indicadores de sesión iniciada y de ya postulado;
  - los de vacante cerrada;
  - los tipos de campos y preguntas;
  - si se puede adjuntar un archivo;
  - los captchas o verificaciones vistos;
  - dónde muestra el portal el **correo de la cuenta** con sesión iniciada;
  - las **páginas del perfil del portal** (hoja de vida, datos personales, formación, experiencia), con sus indicadores de sección incompleta y el enlace de registro de una cuenta nueva;
  - el **modo del CV** en la postulación (`adjunto`, `perfil_unico` o `perfil_multiple` con su límite), cómo se reemplaza o sube y si el empleador ve el CV del momento de postular o el actual del perfil.

  Documentar también qué páginas quedan prohibidas para el motor: contraseña, correo de acceso, privacidad y notificaciones.

  Documentar en `docs/asistente-portales.md`, escribir `assets/selectores/computrabajo.json` y `magneto.json` y fijar `plataformas.<x>.automatica`. Verificar con el documento y los fixtures recortados y sin datos personales en `tests/fixtures/asistente/<plataforma>/` (comprobado con `grep` de nombre, correo, teléfono y documento del dueño).
- [ ] 3.2 Hacer una postulación real controlada por plataforma, con la aprobación expresa del dueño en una vacante que él elija, para capturar la página de confirmación. Verificar con la confirmación guardada como fixture y la postulación visible en "Mis postulaciones".

## 4. IA del usuario (Gemini) y lectura del CV

- [ ] 4.1 Consultar `GET /v1beta/models` con una clave de prueba del dueño, confirmar los modelos de cada tarea con salida JSON y ajustar `config.yaml`. Verificar dejando la lista y la fecha en un comentario.
- [x] 4.2 Crear `asistente/gemini.py`:
  - cliente async por tarea con esquemas pydantic;
  - validación de la clave;
  - manejo de 401/403, de 429 con `retryDelay` y de los timeouts;
  - delimitadores de datos;
  - topes por usuario.

  Verificar con `tests/test_asistente_gemini.py` (respx):
  - el esquema y los delimitadores van en el cuerpo;
  - un 429 corto reintenta y uno largo da `CuotaAgotada`;
  - la clave nunca aparece en logs;
  - un JSON inválido reintenta una vez;
  - el tope se respeta.
- [x] 4.3 Crear `asistente/cv_lectura.py` con pypdf, sus límites, el enmascarado, la detección de escaneado y `leer_cv` → `PerfilExtraido`. Verificar con PDF generados en las pruebas:
  - correo y teléfono enmascarados en el cuerpo enviado;
  - el escaneado pide confirmación;
  - un archivo que no es CV pide otro.

## 5. Vacantes, respuestas y CV

- [ ] 5.1 Crear `asistente/vacantes.py` (índice de `vistas` y retención) y `asistente/detalle.py` (extractores, ritmo, cooldown y caché), con una página de detalle real por fuente en `tests/fixtures/detalle/`. Verificar con respx:
  - cada fixture produce texto;
  - un 403 da `bloqueada`;
  - una vacante finalizada da `cerrada`;
  - una sola consulta por día;
  - sin request durante el cooldown;
  - un id desconocido reindexa una vez.
- [ ] 5.2 Crear `assets/tecnologias.yaml` (unas 200 tecnologías con sinónimos), la tarea `requisitos` con caché compartida y `afinidad.py` determinista con su respaldo sin IA. Verificar con pruebas de porcentaje esperado, sinónimos y respaldo sin IA.
- [ ] 5.3 Crear `asistente/campos.py`, `assets/banco_preguntas.yaml` (unas 60 preguntas) y `asistente/respuestas.py`:
  - cascada;
  - identificación de campos estándar por etiqueta, `name` y tipo;
  - clasificación guardada en el banco;
  - redacción de preguntas abiertas;
  - opciones exactas;
  - "falta dato";
  - origen de cada respuesta.

  Verificar con `tests/test_asistente_respuestas.py`:
  - pregunta conocida sin IA;
  - pregunta nueva clasificada una vez y luego sin IA para otro usuario;
  - una clasificación fuera del catálogo se trata como abierta;
  - opciones exactas;
  - "falta dato" sin inventar;
  - aprendida reutilizada;
  - campos de nombre, correo y archivo identificados sin IA.
- [ ] 5.4 Crear `asistente/cv_adaptado.py` (resumen, hasta 6 habilidades primero y hasta 3 reemplazos, más el validador) y `asistente/cv_pdf.py` (fpdf2, plantilla ATS, Noto Sans con su licencia, 2 páginas y nombre fijo), junto con el CV base al terminar el alta y la carta del paquete. Verificar con `tests/test_asistente_cv.py`:
  - experiencias y proyectos idénticos al base;
  - una tecnología inventada en el resumen hace usar el resumen base;
  - un 4.º reemplazo se ignora;
  - el texto extraído del PDF tiene secciones, tildes y contacto;
  - sin IA se usa el CV base.

  Revisar visualmente un PDF con el dueño.

## 6. API y orquestación en el servidor

- [ ] 6.1 Crear `asistente/api.py` (FastAPI) con el contrato del design 2:
  - página y canje de vinculación;
  - latido con trabajo, versión mínima y versión de selectores;
  - selectores;
  - `tomar` atómico;
  - formulario → respuestas o espera;
  - CV con enlace de un solo uso;
  - pasos y resultado;
  - tokens hasheados, límites y 404 fuera de `/api/v1/`.

  Verificar con `tests/test_asistente_api.py` (TestClient):
  - código vencido o usado;
  - token inválido da 401;
  - cuerpo grande da 413;
  - dos `tomar` simultáneos dan uno solo;
  - el enlace del CV no sirve dos veces;
  - el HTML de evidencia se guarda sin valores de campos.
- [ ] 6.2 Crear `asistente/cola.py` con:
  - estados y transiciones del design 6;
  - `esperando_navegador` por latido ausente y respaldo a las 24 h;
  - `esperando_sesion` según los portales del latido;
  - `esperando_usuario` con `pendientes_usuario` y reencolado;
  - `verificacion` con su plazo;
  - latido cortado con o sin `envio_pulsado`;
  - topes y pausas;
  - modo automático por usuario.

  Verificar con `tests/test_asistente_cola.py`, con un reloj inyectado:
  - cada transición;
  - navegador cerrado antes y después de enviar;
  - dato faltante → pregunta → reencolado;
  - tope diario;
  - modo automático solo sobre el umbral;
  - respaldo a las 24 h sin navegador.
- [ ] 6.3 Configurar Tailscale Funnel en el Fedora hacia `127.0.0.1:8787`. Verificar desde fuera de la red que:
  - `https://<equipo>.<tailnet>.ts.net/api/v1/latido` sin token responde 401;
  - una ruta fuera de `/api/v1/` responde 404.

## 7. Extensión

- [ ] 7.1 Crear `extension/` (Manifest V3):
  - `manifest.json` con los permisos mínimos del design 3;
  - service worker con alarma de 30 s y latido;
  - vinculación automática por la página del servidor y manual por código;
  - popup con el estado;
  - página de opciones con la URL del servidor;
  - detección de sesión por portal según los selectores.

  Verificar con pruebas `navegador` (Playwright carga la extensión sobre una API de prueba):
  - se vincula sola al abrir la página de vinculación;
  - el latido informa los portales con sesión según los fixtures;
  - la extensión no tiene permisos fuera de los dominios declarados.
- [ ] 7.2 Crear `extension/motor.js`, un motor de pasos declarativos:
  - espera, clic y lectura de campos con etiqueta, tipo y opciones;
  - llenado con eventos nativos y pausas;
  - adjunto con `DataTransfer`;
  - marca `envio_pulsado` antes del envío;
  - espera de la confirmación;
  - detección de captcha con pestaña visible y sondeo hasta resolverse;
  - reporte de pasos y errores con el HTML sin valores.

  Verificar con pruebas `navegador` sobre formularios HTML de prueba:
  - llena todos los tipos de campo y el servidor de prueba recibe los valores;
  - el captcha simulado detiene y continúa al quitarse;
  - un selector ausente reporta `formulario_desconocido`;
  - el HTML reportado no contiene los valores escritos.
- [ ] 7.3 Crear `extension/adaptadores/computrabajo.js` con los selectores de `assets/selectores/computrabajo.json`. Verificar con pruebas `navegador` sobre los fixtures de 3.1 y 3.2:
  - la postulación completa llega a `enviada`;
  - detecta ya postulado, cerrada y sesión no iniciada.
- [ ] 7.4 Crear `extension/adaptadores/magneto.js` con las mismas condiciones y pruebas que 7.3.
- [ ] 7.5 Implementar la detección `sin_sesion`, `incompleto` y `listo` por portal y el trabajo `completar_perfil` en ambos adaptadores, más su encolado prioritario en `asistente/cola.py`:
  - carga del CV base;
  - datos personales, formación y experiencia desde el perfil;
  - solo agregar o llenar vacíos;
  - preguntas de datos faltantes por el bot.

  Verificar con pruebas `navegador` sobre fixtures de perfil:
  - un perfil sin hoja de vida queda completo;
  - una experiencia existente no se borra ni se modifica;
  - el motor se niega a operar en páginas prohibidas;
  - el bot envía la guía con el enlace de registro cuando el estado es `sin_sesion` sin cuenta.
- [ ] 7.6 Implementar los pasos `cv_subir` y `cv_verificar` del motor según `cv.modo`, con el respeto de los CV del usuario en `perfil_multiple` y la autorización `actualizar_cv_portal` (pregunta en el alta y en `/perfil`). Verificar con pruebas `navegador` sobre fixtures de cada modo:
  - en `perfil_unico`, con autorización, el CV queda reemplazado antes del envío;
  - en `perfil_multiple`, con el límite alcanzado, solo se reemplaza el subido por el sistema;
  - sin autorización, no se toca el CV y el registro lo indica;
  - si la verificación falla, se postula con el existente y se registra.

- [ ] 7.7 Implementar la cuenta del portal asociada:
  - lectura del correo (`cuenta.correo` en los selectores) en ambos adaptadores;
  - tabla `cuentas_portal` con correo cifrado y hash;
  - confirmación inicial por el bot;
  - verificación antes de cada trabajo y estado `cuenta_distinta` con enmascarado y botones;
  - el correo por plataforma en `/estado` y `/perfil`.

  Verificar con pruebas `navegador` y de cola:
  - la primera detección pide confirmar y luego asocia;
  - una sesión con otro correo no postula y avisa con el correo enmascarado;
  - "Es mi cuenta nueva" reasocia y reencola;
  - sin correo legible da `formulario_desconocido`;
  - el correo ajeno no se guarda en la base.

## 8. Bot asistente

- [ ] 8.1 Crear `asistente/bot.py`:
  - `/start` con `v_` e `i_`;
  - comprobación de membresía antes de todo;
  - alta guiada (política → clave con borrado del mensaje → CV → secciones → enfoque → cuestionario con botones y reanudable → instalar y vincular la extensión con guía → estado de cada portal: crear cuenta, completar perfil o listo);
  - respuesta en grupos;
  - límite de mensajes por minuto;
  - `Forbidden`.

  Verificar con pruebas de handlers sobre updates simulados:
  - un no miembro recibe "exclusivo del grupo";
  - el nuevo usuario desde ⚡ retoma la vacante al terminar el alta;
  - el mensaje con la clave se borra;
  - el cuestionario se retoma;
  - el grupo solo recibe "escríbeme en privado".
- [ ] 8.2 Flujo del toque ⚡:
  - decisión entre automática y respaldo;
  - mensaje de progreso editado en el lugar ("En cola", "Se enviará cuando abras tu navegador", "Postulando…", resultado);
  - resultado con las preguntas, las respuestas y su origen;
  - preguntas de datos faltantes con botones y texto;
  - avisos de sesión no iniciada y de verificación pendiente;
  - paquete de respaldo con su motivo y "Responder preguntas del formulario".

  Verificar con pruebas de punta a punta con Telegram, Gemini y la API simulados:
  - caso normal sin acciones extra;
  - PC apagado y luego encendido;
  - LinkedIn → respaldo;
  - dato faltante → pregunta → enviada;
  - tres usuarios simultáneos sin mezclarse.
- [ ] 8.3 Comandos:
  - de usuario: `/perfil`, `/cuestionario`, `/clave`, `/cv`, `/navegadores`, `/vincular`, `/automatico [umbral]`, `/historial`, `/detalle <n>`, `/estado`, `/pausa` y `/borrarme`;
  - botones de seguimiento y el recordatorio único;
  - del dueño: `/usuarios`, `/suspender`, `/reactivar`, `/stats` y `/plataformas`, con auditoría, más los avisos de `formulario_desconocido` con evidencia;
  - ayuda ante un comando desconocido.

  Verificar con pruebas de que:
  - un comando de administración ajeno responde como desconocido;
  - `/detalle` muestra los pasos, las respuestas con su origen y el CV;
  - `/borrarme` borra todo.
- [ ] 8.4 Crear `asistente/servicio.py`, `buscador.py asistente servicio|enlace <clave>` y `asistente selectores recargar`:
  - bot, API y tareas periódicas en un solo proceso asyncio;
  - salida inmediata si `activo` es falso;
  - mensaje de instalación si faltan dependencias;
  - cierre limpio.

  Verificar con una prueba de arranque y parada y una ejecución local contra un bot de prueba.

## 9. Resumen, despliegue y pilotos

- [ ] 9.1 Agregar a `resumen.py` las métricas agregadas del asistente:
  - usuarios activos y altas;
  - navegadores en línea;
  - postulaciones enviadas y de respaldo;
  - verificaciones;
  - % de respuestas sin IA;
  - preguntas nuevas del banco.

  Verificar con `tests/test_resumen.py`:
  - día con actividad;
  - asistente desactivado con el resumen idéntico al de antes;
  - el cuerpo a DeepSeek no contiene ids ni nombres.
- [ ] 9.2 Crear `deploy/buscador-asistente.service` y la sección del asistente en `deploy/INSTALAR.md`:
  - BotFather;
  - agregar el bot asistente como administrador sin permisos del grupo privado;
  - clave maestra y su **respaldo**;
  - Tailscale Funnel;
  - configuración y servicio;
  - selectores y cómo corregirlos;
  - operación, administración, borrado y rollback.

  Crear `docs/guia-usuario.md` (clave de Gemini, instalar en Edge o cargar en Chrome, vincular, crear la cuenta del portal si no existe, iniciar sesión, mantener el navegador abierto). Actualizar `README.md`. Verificar con `uv run pytest`, `uv run ruff check` y `uv run ruff format --check`.
- [ ] 9.3 Piloto privado con `activo: true` y `enlace_canal: false`: el dueño hace el alta, carga la extensión descomprimida en Edge, la vincula y toca ⚡ (con `asistente enlace`) en 3 vacantes reales de cada plataforma automática. Verificar:
  - las 6 terminan `enviada` sin acciones extra (salvo los datos nuevos la primera vez);
  - aparecen en "Mis postulaciones";
  - el CV adjunto es el adaptado y sin datos inventados;
  - el tiempo es menor a 2 minutos con el navegador en línea.
- [ ] 9.4 Piloto con 2 o 3 invitados (carga descomprimida) durante al menos 3 días. Verificar que no hay errores sin resolver en el log, recoger sus comentarios y ampliar el banco con las preguntas nuevas que llegaron a la IA.
- [ ] 9.5 Registrar la cuenta gratuita en Microsoft Partner Center (por el dueño), publicar la extensión en la tienda de Edge (oculta si la opción existe) con la política de 2.2 y poner el enlace en `extension.url_edge`. Luego habilitar `enlace_canal: true`. Verificar que:
  - un usuario la instala desde el enlace con "Obtener";
  - cada ficha de la siguiente publicación trae ⚡;
  - un toque de un usuario vinculado termina en `enviada`;
  - el resumen del día siguiente muestra las métricas del asistente.
