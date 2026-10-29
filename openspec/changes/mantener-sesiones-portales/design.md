## Context

La sesión de cada portal vive en las cookies del Chrome del usuario. La extensión (MV3, `servicio.js`) solo la **observa**: cada 6 h (`REVISION_MAX_MS`) y antes de cada trabajo abre el portal en una pestaña de fondo (`revisarPortal`) y `motor.js` decide `listo` o `sin_sesion` por la marca de sesión o la URL de ingreso. Nada en el código cierra sesión (no hay ningún clic a «Cerrar sesión»). El servidor guarda el estado por navegador en `portales_json` y, en `api.py` (`latido`), avisa por Telegram al pasar a `listo`/`incompleto`, pero al pasar a `sin_sesion` solo guarda el estado y sigue (`continue`): no hay aviso de pérdida.

La causa real de la pérdida no se conoce y puede ser distinta por portal. Hipótesis: (a) cookie de autenticación **de sesión** (sin `Expires`/`Max-Age`) que muere al cerrar Chrome; (b) vencimiento del servidor corto, absoluto o por inactividad; (c) el ajuste de Chrome «Borrar cookies al cerrar todas las ventanas»; (d) dos perfiles de Chrome (el dueño ya tropezó con eso: la extensión y las sesiones están en un solo perfil). La extensión no declara el permiso `cookies`, así que hoy no puede distinguirlas.

La extensión se distribuye a otros usuarios (ficha de la tienda de Edge): cualquier permiso nuevo tiene que ser opcional.

## Goals / Non-Goals

**Goals:**
- Saber, por portal, cuál de las hipótesis es la causa, con datos y no con suposiciones.
- Que las sesiones sobrevivan al cierre de Chrome y a la inactividad cuando el portal lo permita.
- Que el usuario se entere (con motivo) cuando una sesión se pierde.

**Non-Goals:**
- Evadir un vencimiento absoluto del servidor, renovar sesiones con credenciales o guardar contraseñas: si el portal cierra la sesión, el usuario inicia sesión él mismo.
- Leer, guardar o enviar valores de cookies, o sacar cookies del navegador del usuario.
- Cambiar los ajustes de Chrome del usuario.
- Persistir cookies de portales que el usuario no activó, o de la plataforma «externa».

## Decisions

**1. Permiso `cookies` en `optional_permissions`, con origen por portal ya concedido.** `chrome.cookies` necesita el permiso `cookies` más el permiso de host del portal; el segundo ya existe (`tienePermiso`). Se pide el primero con `chrome.permissions.request` al activar el diagnóstico o el interruptor, igual que ya se hace con los portales. *Alternativa descartada:* declararlo obligatorio: desactiva la extensión de todos los usuarios hasta que lo acepten y obliga a una nueva revisión en la tienda.

**2. Qué cookies se tratan: una lista por portal en los selectores, no todas.** `assets/asistente/selectores/<portal>.json` gana `sesion.cookies`: nombres de las cookies de autenticación (más dominios si hace falta). El diagnóstico lista **todas** las cookies del portal (solo metadatos) para que la primera medición sirva para llenar esa lista; la persistencia solo toca las nombradas. *Alternativa descartada:* persistir todas las cookies de sesión del dominio: incluye cookies de seguimiento o antifalsificación que no deben durar y amplía el riesgo sin necesidad. Como son datos versionados del servidor, corregir la lista no exige publicar otra versión de la extensión.

**3. Persistir con `chrome.cookies.set` sobre la misma cookie.** Se lee la cookie con `chrome.cookies.get`, y se vuelve a escribir con los mismos `name`, `value`, `domain` (omitido si es host-only), `path`, `secure`, `httpOnly`, `sameSite`, `storeId` y `partitionKey` más `expirationDate = ahora + sesion.persistir_dias` (30 por defecto; Chrome limita a 400). El valor pasa por memoria en la misma llamada y no se guarda. Un `chrome.cookies.onChanged` con la cookie nombrada, `removed: false` y `cookie.session === true` dispara de nuevo la reescritura; como la reescritura deja la cookie como persistente, no se produce un bucle. *Alternativa descartada:* un servicio externo o un proxy que reescriba `Set-Cookie`: sale del navegador y toca las credenciales.

**4. El mantenimiento reutiliza la revisión existente.** `revisarPortal` ya visita cada portal cada 6 h. Con «Mantener la sesión» activa se añade un intervalo por portal (`sesion.mantener_min`, por defecto el actual) y se aplaza si `ocupado` (una postulación en curso). Antes y después de la visita se comparan los vencimientos de las cookies nombradas: si avanzaron, el portal renueva por uso (se registra en `chrome.storage.local`); si no, el vencimiento es absoluto y no hay nada que mantener. *Alternativa descartada:* una alarma nueva con su propia pestaña: duplica pestañas en segundo plano y el riesgo de molestar al usuario.

**5. Distinguir la causa al perder la sesión.** Al pasar a `sin_sesion` la extensión mira las cookies nombradas: ausentes tras reinicio con marca de «persistida por la extensión» → `borrada_al_cerrar` (Chrome las borra al salir); presentes con vencimiento pasado → `vencida`; presentes y vigentes → `cerrada_por_el_portal`; eran de sesión sin persistencia → `cookie_de_sesion`. El motivo viaja en el campo `motivo` del latido, que ya existe en `api.py` (`Portal.motivo`, hasta 40 caracteres); el servidor no necesita campos nuevos para recibirlo. La marca de «persistida» es un contador por portal en `chrome.storage.local`, no la cookie.

**6. El aviso de sesión perdida vive en el servidor (`api.py`, `latido`).** Se aprovecha `aviso` (último estado con sesión) que ya existe: si el estado previo (`aviso`) era `listo`/`incompleto` y llega `sin_sesion`, se notifica `portal_sin_sesion` con el motivo y se evita repetir mientras siga cerrada. Si hay una postulación en `esperando_sesion` de ese portal, el texto va en su tarjeta de espera (`espera.py` ya maneja `SIN_SESION`) y no como mensaje aparte. Los textos nuevos van en `textos.py`.

**7. Privacidad hacia el servidor.** Solo viajan el estado de la sesión y el código del motivo. La clasificación («dura hasta»/«se pierde al cerrar») se calcula en la extensión y no se envía el nombre de las cookies ni los valores.

## Risks / Trade-offs

- **[Una sesión persistente dura más y alguien con acceso al PC la puede usar]** → opt-in por portal, apagado por defecto, advertencia en el interruptor, y el vencimiento largo es configurable.
- **[`chrome.cookies.set` falla o cambia una cookie con `partitionKey` o prefijo `__Host-`/`__Secure-`]** → se reescribe con los mismos atributos y, si falla, se registra el error y se informa «No pude mantener la sesión» en la tarjeta en vez de fallar en silencio.
- **[El portal ignora el vencimiento largo del lado del servidor]** → el diagnóstico lo muestra (`cerrada_por_el_portal`); no se promete lo que no se puede cumplir y el aviso de pérdida sigue funcionando.
- **[Chrome borra las cookies al salir]** → no se puede arreglar desde la extensión; se detecta (`borrada_al_cerrar`) y se le dice al usuario cómo añadir el portal a las excepciones.
- **[El service worker MV3 se duerme y se pierde un `onChanged`]** → el oyente se registra al cargar el módulo (síncrono, nivel superior) y, además, cada revisión de 6 h vuelve a pasar por la reescritura.
- **[Los nombres de las cookies cambian con un rediseño del portal]** → viven en los selectores del servidor; el diagnóstico completo permite detectar el cambio.

## Migration Plan

1. La primera entrega solo trae el diagnóstico y el aviso de pérdida (sin tocar cookies): se mide uno o dos días con el permiso concedido en el Chrome del dueño.
2. Con los resultados se rellenan `sesion.cookies` por portal y se activa la persistencia, portal por portal, empezando por elempleo y Magneto.
3. Reversión: el interruptor apagado deja de reescribir cookies al instante; quitar el permiso `cookies` desactiva todo y las cookies vuelven a ser lo que el portal emita en el siguiente inicio de sesión. Subir la versión de la extensión (manifiesto y paquete de la tienda) se hace al final de cada paso.

## Open Questions

- ¿Qué vencimiento largo por defecto conviene (30 días propuesto)? Se puede ajustar con los datos del diagnóstico sin cambiar la estructura.
- ¿Qué portales (además de elempleo y Magneto) pierden la sesión? El diagnóstico lo dirá; no cambia el diseño.
