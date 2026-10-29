## Context

`revisarPortal` (servicio.js) abre `/in/me/` en una pestaña en segundo plano, espera hasta 10 s a que la URL tenga el usuario (`esperarPerfil`), navega a `{perfil}/overlay/contact-info/` y espera hasta 10 s a que aparezca `a[href^='mailto:']` (`esperarCorreo`). Lo observado en vivo (ver proposal.md) es que el salto es un `history.replaceState` y que el `<a mailto:>` lo crea el JavaScript de LinkedIn; el HTML del servidor ya trae el correo dentro del payload de RSC, como `\"url\":\"mailto:…\"`. Medido con la sesión del dueño: el HTML de `/in/<usuario>/overlay/contact-info/` trae 1 `mailto:`; el de `/in/me/overlay/contact-info/` y el del perfil, 0; el de `/in/me/` trae `linkedin.com/in/<usuario>` como único perfil distinto.

No se pudo reproducir con certeza la pestaña oculta desde Claude in Chrome (la herramienta activa la pestaña sobre la que actúa), así que el diseño no depende de saber cuál de los dos pasos falla: la lectura nueva no necesita ninguno.

## Goals / Non-Goals

**Goals:** leer el correo con la pestaña oculta; dejar en el latido por qué falta; no esperar 6 h para reintentar.

**Non-Goals:** usar la API interna de LinkedIn (`/voyager/api`), que exige el token CSRF y cambia sin aviso; cambiar cómo se leen los demás portales; tocar el servidor más allá del json.

## Decisions

1. **Leer el HTML con `fetch` desde la pestaña del portal**, no desde el service worker. Desde la pestaña es una petición del mismo origen con las cookies del usuario, sin depender de cómo Chrome trata las cookies `SameSite` en peticiones de la extensión. Alternativa descartada: hacer visible la pestaña (molesta al usuario y no garantiza el pintado).
2. **Declarativo en `cuenta.html`** de `linkedin.json`: `inicio` (`/in/me/`), `perfil_ruta` (usuario desde la ruta actual), `perfil_html` (usuario dentro del HTML de inicio; gana el más repetido, sin `me`), `url` (`/in/{perfil}/overlay/contact-info/`) y `correo` (expresión con un grupo). El motor solo sabe «pedir, extraer, validar». Un cambio de LinkedIn se arregla con datos.
3. **Exactamente un correo válido** (pasa `correoValido` y `dominios_ajenos`), sin duplicados. La página de contacto del propio perfil trae uno; si un día trae varios, es más seguro no adivinar (`varios_correos`).
4. **Orden**: primero la lectura por HTML justo después de confirmar la sesión; si no da correo, sigue el recorrido actual de la 1.3.2 como respaldo. El motivo que se informa es el de la lectura por HTML.
5. **Petición que acaba en ingreso** (`response.url` en `url_sin_sesion`) → `sin_sesion` en el motivo, pero el estado del portal lo sigue decidiendo `revisar`, para no cambiar la detección de sesión.
6. **Reintento**: `estadoPortales` considera vencido un portal `listo` sin correo cuya revisión tiene más de 10 minutos (`REVISION_SIN_CORREO_MS`).

## Risks / Trade-offs

- [LinkedIn cambia el formato del payload] → La expresión vive en `linkedin.json`; el motivo `sin_correo` lo delata en el servidor y el respaldo pintado sigue activo.
- [El HTML de `/in/me/` trae otros perfiles (sugeridos)] → Primero se usa el usuario de la URL; en el HTML gana el más repetido (el propio aparece cientos de veces) y el correo solo se acepta de la página de contacto de ese perfil, que es la del propio usuario.
- [Dos peticiones de ~1,5 MB por revisión] → Solo en la revisión de la cuenta, cada 6 h o cada 10 min mientras falte el correo.
- [Reintento cada 10 min abre una pestaña en segundo plano] → Solo mientras falte el correo; con el correo encontrado vuelve a 6 h.

## Migration Plan

1. Unir el PR y hacer `git pull` en el Fedora y reiniciar el servicio (entrega el `linkedin.json` nuevo).
2. El dueño recarga la extensión sin empaquetar (1.3.3) en `chrome://extensions` y pulsa recargar en el popup.
3. Verificar en `navegadores.portales_json` que LinkedIn pasa a `por_confirmar`, o leer el motivo.

Vuelta atrás: quitar `cuenta.html` del json deja el comportamiento de la 1.3.2.
