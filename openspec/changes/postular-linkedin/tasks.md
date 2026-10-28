## 1. Requisitos previos

- [x] 1.1 🟢 Reconciliar la exclusión de LinkedIn (design.md, decisión 1): si `conectar-plataformas-extension` y `asistente-postulacion-telegram` ya están archivados, añadir aquí el delta `MODIFIED` de `postulacion-automatica` que quita «LinkedIn MUST NOT habilitarse»; si no, editar esa frase en sus specs con la nota que remite a este change. Verificar con `openspec validate postular-linkedin --strict`. *(2026-10-25: seguían sin archivar; se editó la exclusión en sus specs con la nota.)*
- [x] 1.2 🟢 Confirmar que `motor-generico-autorreparable` está aplicado y que `familia_de` y `limpiar_destino` existen (tarea 2.2 de `medir-destinos-linkedin`); si faltan, aplicarlas primero. Verificar con sus pruebas en verde. *(2026-10-25: faltaban; se adelantaron las tareas 2.2 y 3.1 de `medir-destinos-linkedin`.)*

## 2. Configuración y plataforma

- [x] 2.1 🟢 `config.yaml` y `comun/config.py`: `asistente.plataformas.linkedin: {automatica: false}`, `asistente.linkedin` (`tope_diario: 15`, `pausa_min_s: 240`, `familias_con_cuenta`, `mensajeria`, `hosts_prohibidos`) y `medicion_linkedin.familias` con `ashby`, `grnh.se`, `typeform`, `pandape`. Verificar con `tests/comun/test_config.py`.
- [x] 2.2 🟢 `asistente/vacantes.py`: `linkedin.com` → `linkedin`. Verificar con `tests/asistente/test_detalle.py`, donde ya se prueba `plataforma_de_url` (las filas viejas sin plataforma también se deducen).

## 3. Lectores de esquema

- [x] 3.1 🟡 `tests/fixtures/ats/`: respuestas recortadas de la API de Greenhouse, de la consulta de Ashby y del `rendererData` de Typeform (del reconocimiento del 2026-10-21), sin datos personales. Pruebas que fallan primero en `tests/asistente/test_esquemas_ats.py`: preguntas, tipos, opciones, obligatoriedad y claves. Verificar que fallan.
- [x] 3.2 🟡 `asistente/esquemas_ats.py`: traducción de Greenhouse, Ashby y Typeform y cliente con `Ritmo` por dominio; un error deja la postulación sin esquema. Verificar con 3.1 en verde y una prueba `respx` de API caída.
- [x] 3.3 🟡 Lever: reconocer sin sesión (GET, una petición cada ~8 s) una página `jobs.lever.co/{empresa}/{id}/apply` de una vacante real del canal o de la medición, guardar el recorte y escribir su traducción. Verificar con su prueba y la nota en `docs/asistente/portales.md`.
- [x] 3.4 🟢 `assets/asistente/familias_ats.json` (CV, botón de enviar y señal de éxito de Greenhouse, Ashby, Lever y Typeform), entregado con su versión y validado. Verificar con `test_plataformas.py`.

## 4. Servidor: destino, clasificación y reglas de LinkedIn

- [x] 4.1 🟡 Tabla `destinos_linkedin` y `POST /postulaciones/{id}/destino`: limpiar, guardar, clasificar (mensajería, familia con cuenta, dominio barrera, genérico) y responder `respaldo`, `esperar_usuario` o `abrir` con familia, esquema, receta y datos de familia. Verificar con `test_api.py` (los escenarios de «Clasificador de destino»).
- [x] 4.2 🟡 `asistente/nucleo.py`: camino de LinkedIn al tocar ⚡ (aceptación, interruptores, destino guardado con comprobación de `jobPosting/{id}` y cooldown, esquema anticipado y card antes de encolar), tope diario, pausa mínima y pausa de 24 h. Verificar con `test_nucleo.py`.
- [x] 4.3 🟡 Conversación y card: aceptación del riesgo («Acepto y postular» / «Solo paquete», con versión y fecha), `/linkedin` con los dos interruptores, motivos nuevos (`linkedin_sin_aceptar`, `linkedin_apagado`, `destino_mensajeria`, `sin_permiso_externo`, `salto_de_dominio`, `oauth`) y la política de datos con versión nueva. Verificar con `test_bot.py` y `test_tarjeta_postulacion.py`.

## 5. Extensión

- [x] 5.1 👤 Reconocimiento con la sesión del dueño (Claude in Chrome o el dueño), sin enviar: página de una vacante sencilla y una externa, el modal de Solicitud sencilla hasta la pantalla de revisión (sin pulsar «Enviar solicitud»), la elección de CV, «Seguir a la empresa» y el aviso de seguridad si aparece. Guardar recortes sin datos personales en `tests/fixtures/linkedin/` y anotar en `portales.md`. Verificar con los recortes y la nota. *(2026-10-25, parcial: hecho todo menos la pantalla de revisión de un modal de varios pasos y el aviso de seguridad. La cuenta no tiene CV guardado y subir uno entregaría datos; recortes en `tests/fixtures/linkedin/` y nota en `portales.md`. Falta repetirlo con un CV guardado en LinkedIn. 2026-10-27, completada: con el CV del dueño subido a mano en cada solicitud (LinkedIn no lo conserva si se descarta) se llegó a «Revisa tu solicitud» en una sencilla de 4 pasos, con «Seguir a la empresa» marcada por defecto; nota en `portales.md`. Sin ver: el aviso de seguridad y el mensaje de enviada, que no se provocan sin enviar. No se guardaron recortes nuevos porque la revisión muestra datos personales.)*
- [x] 5.2 🟡 `assets/asistente/selectores/linkedin.json`: sesión, tipo de solicitud, enlace `/safety/go`, cerrada, pausada, aviso de seguridad, modal, botones, confirmación, «Seguir a la empresa», hosts prohibidos y `cv.modo`. Verificar con `test_plataformas.py`.
- [x] 5.3 🔴 `extension/portales.js`, `servicio.js` y `popup.js`: plataforma `externa` (permiso `https://*/*`, `PROHIBIDAS` ampliada, hosts prohibidos y regla de salto), paso de LinkedIn a `/destino` y navegación de la misma pestaña al destino con `bucleGenerico`, Solicitud sencilla con el contenedor fijado en el modal, y pedido del permiso desde el popup con su explicación. Verificar con pruebas de Playwright en `test_extension.py` sobre los recortes de 5.1 y las copias de `tests/fixtures/formularios/` (externa hasta la página de gracias falsa, salto de dominio detenido, OAuth detenido, sencilla hasta la confirmación falsa con «Seguir a la empresa» desmarcado). *(2026-10-27: hecha; 176 pruebas con navegador y 533 del servidor en verde. La cuenta de LinkedIn se lee del `mailto:` de `/in/me/overlay/contact-info/`, supuesto por verificar al empezar el ensayo 6.2.)*
- [x] 5.4 🟢 `extension/manifest.json` 1.3.0 con `https://*/*` en `optional_host_permissions`. Verificar con la prueba de manifiesto.

## 6. Verificación y pilotos

- [x] 6.1 🟡 Suite completa en segundo plano (`.venv/Scripts/python -m pytest`) y `.venv/Scripts/ruff check`. Verificar con las dos en verde. *(2026-10-28: ruff limpio; suite sin fallos nuevos: 1939 + 104 de la extensión + 30 del bucle genérico en verde. Solo fallan los 3 de `tests/radar` (hermes CLI y punto de entrada), que ya fallan en main en Windows. Las pruebas de Playwright son lentas y fallan en masa si compiten con otro Chrome o si desaparece la carpeta: repetirlas solas.)*
- [ ] 6.2 👤 Desplegar en el Fedora con LinkedIn en ensayo solo para el dueño, aceptar el riesgo, conceder el permiso amplio y dejar dos semanas de ensayo. Verificar con la cobertura por familia en el resumen diario y anotarla en `portales.md`.
- [ ] 6.3 👤 Reales del dueño: 3 por Solicitud sencilla y 3 por páginas externas que terminen `enviada`, comprobadas en LinkedIn («Mis empleos») o en el correo de confirmación del ATS. Verificar y anotar en `portales.md`.
- [ ] 6.4 👤 Invitados: avisar del riesgo, `plataformas.linkedin.automatica: true` para todos y 3 días sin errores sin resolver. Verificar con el resumen diario y anotar el cierre del piloto.
