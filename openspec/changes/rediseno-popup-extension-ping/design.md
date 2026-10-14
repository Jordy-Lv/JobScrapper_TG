## Context

Ver `proposal.md` para el motivo. Estado actual observado en el código:

- `extension/popup.html|css|js` ya tienen tarjetas por portal (logo, pill de estado, engranaje a la vista del portal), botón de pausa, botón flotante de Telegram y la línea «Conectado · hace N min». Esa línea sale de `estado.en_linea` y `estado.ultimo_latido`, que escribe `servicio.js` en cada latido (`enviarLatido`); no mide nada en vivo.
- El popup ya pide un latido forzado con `chrome.runtime.sendMessage({ tipo: "latido", revisar: true })` (botón «Revisar»); `latido()` del service worker deduplica llamadas simultáneas (`enCurso`).
- `api.js` centraliza el `fetch` al servidor (`llamar`, con prefijo `/api/v1`, `servidor` guardado en `chrome.storage.local`). El permiso del host del servidor ya está en `host_permissions`, así que el popup puede hacer `fetch` directo.
- `api.py` no tiene ningún endpoint público ligero: `GET /vincular/{codigo}` y `GET /privacidad` devuelven HTML, y el resto exige token. El limitador por IP (`Limitador`) ya se usa en `/vincular`.
- Las pruebas del popup (`tests/test_extension.py`, marca `navegador`) cargan la extensión real en un navegador contra un servidor FastAPI simulado (fixture `servidor`/`api`) y abren `chrome-extension://<id>/popup.html`.

La maqueta del dueño es una imagen generada; fija la estética (marca, bordes de color, disposición), no el comportamiento. Donde la maqueta y el comportamiento actual difieren (por ejemplo, la tarjeta «Sin sesión» sin acción), se conserva el comportamiento.

## Goals / Non-Goals

**Goals:**
- Aplicar la estética de la maqueta al popup sin perder ninguna función actual.
- Mostrar la latencia real con el servidor y permitir recargar la conexión desde la parte superior.
- Que el ping funcione aunque el servidor aún no tenga el endpoint nuevo.

**Non-Goals:**
- Cambiar el protocolo de latido, el motor de postulación, los permisos o el nombre de la extensión en el manifiesto y la tienda.
- Medir la latencia en segundo plano ni guardar historial de pings.
- Habilitar los portales «Próximamente» ni cambiar qué portales soporta el servidor.
- Rediseñar la vista de configuración de un portal (engranaje de la tarjeta) ni la página de opciones, más allá de heredar los colores.

## Decisions

**1. El ping es un `fetch` cronometrado desde el popup a `GET /api/v1/ping`, no el tiempo del latido.**
El latido hace trabajo en el servidor (autenticación, base de datos, asignación de trabajo) y a veces revisa portales, así que su duración no es la latencia de red. Un endpoint vacío mide la ida y vuelta real a través del túnel de Tailscale. Se mide con `performance.now()` alrededor del `fetch`, con `AbortController` a 5 s. Alternativa descartada: reutilizar el latido (no requiere servidor nuevo, pero mezcla red con carga del servidor y gasta un latido por cada apertura).

**2. Cualquier respuesta HTTP cuenta como alcanzado.**
Si el servidor aún no se ha desplegado con la ruta nueva, devuelve 404 (también cuando falla la limitación con 429); esa ida y vuelta sigue siendo la latencia real. Solo el error de red o el tiempo agotado cuentan como «Sin respuesta». Así el orden de despliegue (extensión primero o servidor primero) no importa y la tarea del dueño no bloquea nada.

**3. `ping()` vive en `api.js`; el resultado se guarda en `chrome.storage.local` bajo `ping` (`{ ms, ok, en }`).**
`api.js` ya es el único lugar que construye URLs del servidor. Guardar el último valor permite pintar el popup al instante con el dato anterior mientras llega el nuevo, y que `chrome.storage.onChanged` (que ya dispara `pintar`) refresque la barra sin lógica extra. El ping usa `fetch` con `credentials: "omit"` y sin cabecera `Authorization`, por lo que no puede filtrar el token.

**4. Cuándo se mide: al abrir el popup y al tocar recargar.**
No hay medición periódica: el popup vive segundos y el service worker no debe despertarse por esto. Si la medición al abrir no ha terminado, se muestra el valor guardado (o «Midiendo…» si nunca hubo uno).

**5. Recargar = ping + latido forzado con revisión, en ese orden, con estado «Reconectando…».**
Primero se mide el ping (feedback inmediato de si el servidor está vivo) y luego se pide `{ tipo: "latido", revisar: true }`, que ya deduplica y revisa portales. La barra pasa por tres estados (midiendo, reconectando, resultado). Un indicador `recargando` en memoria evita el doble toque. Este botón **reemplaza** al «Revisar» de la sección Portales, que hace la misma revisión (abre cada portal en una pestaña de fondo para releer sesión y correo, y manda un latido): se retira «Revisar» y el botón de recarga es un icono ↻ que gira mientras trabaja, con `title` y `aria-label` «Recargar la conexión».

**6. Endpoint `GET /api/v1/ping` público, mínimo y limitado por IP.**
Devuelve `{"ok": true}`, no toca la base de datos, no usa `navegador_actual` (por tanto no actualiza `ultimo_latido`) y reutiliza `Limitador` por IP con un tope propio y holgado (por ejemplo 60 por minuto) para que un abuso no afecte al resto. Al estar expuesto por el túnel público, no devuelve versión, hora ni configuración.

**7. Rediseño sobre el CSS existente, con color de borde por portal en variables.**
Se mantiene `popup.css` (no se introduce un framework): ancho del popup 360 px, fondo oscuro con resplandor azul, tarjetas con fondo translúcido y `border` + `box-shadow` del color de cada portal (variable `--color-portal` en `.tarjeta.<portal>`). Colores de la maqueta: Computrabajo azul, Magneto verde, elempleo cian, GetOnBoard coral, LinkedIn azul, Servicio de Empleo rojo. El engranaje de la cabecera abre `chrome.runtime.openOptionsPage()`. El botón de Telegram y la «Última: …» se mantienen en posición fija abajo, con la píldora a la izquierda y el botón a la derecha, y el contenido recibe un `padding-bottom` para que no quede tapado.

**8. La marca «APOLO TI» se aplica solo dentro del popup.**
El nombre del proyecto en `pyproject.toml` ya es «APOLO TI», pero `manifest.json`/`_locales` y la ficha de la tienda usan «Asistente de postulación». Cambiarlo allí afecta a la publicación en la tienda (tarea 9.5) y se decide aparte. Se actualiza el `<title>` y el `<h1>` del popup. El dueño entregó el logo definitivo de APOLO TI (maletín con radar, mira y corchetes de código sobre fondo oscuro, con el texto «APOLO TI · Software Engineering · Tech Careers»). Para el popup y los iconos 16/32/48/128 se usa solo el emblema, recortado sin el texto (a 16 px el texto es ilegible) y centrado sobre fondo oscuro; el logo completo con texto se reserva para la ficha de la tienda.

## Risks / Trade-offs

- [El ping mide hasta el túnel/servidor y no la salud de todo el asistente] → La barra dice «Conectado» solo cuando hay respuesta; el estado de los portales sigue viniendo del último latido y se refresca con la recarga.
- [La primera medición tras abrir el popup puede tardar hasta 5 s si el servidor no responde] → Se pinta de inmediato el último valor guardado con la marca de «Midiendo…» y las tarjetas no esperan a la medición.
- [Un 404 o 429 del servidor se mostrará como «Conectado» con su latencia] → Es intencional (decisión 2); el 429 solo ocurre con abuso desde la misma IP.
- [Endpoint público sin autenticación expuesto por Tailscale Funnel] → Respuesta fija, sin base de datos y con límite por IP; no revela datos.
- [Una pantalla más cargada puede desbordar el popup (máximo del navegador ≈ 600 px de alto)] → Con seis tarjetas se compacta el espaciado y la lista hace scroll interno si hace falta; se verifica con una captura a 360 px.
- [Cambios visuales rompen las pruebas del popup que buscan elementos por clase o texto] → Se conservan los ids y las clases que usan las pruebas actuales (`#portales`, `.tarjeta`, `.pill`, `#linea-texto`, `#vp-*`) o se actualizan en la misma tarea.

## Migration Plan

1. Fusionar el código. La extensión nueva funciona contra el servidor actual (decisión 2): el ping mostrará la latencia de una respuesta 404 hasta que se despliegue.
2. El dueño actualiza el servidor en el PC Fedora (`git pull` y reiniciar el servicio del asistente) para que `/api/v1/ping` devuelva 200.
3. Recargar la extensión descomprimida en el navegador del dueño y comprobar visualmente.
4. Rehacer las capturas de `docs/tienda-edge/` antes de enviar la ficha de la tienda.

Reversión: volver al commit anterior de la extensión; el endpoint nuevo es inofensivo y puede quedarse.

## Open Questions

Ninguna.
