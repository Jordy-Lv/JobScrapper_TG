## Context

La causa está en proposal.md. La detección de sesión vive en `extension/motor.js`:

- `sinSesion(sel)` devuelve «sin sesión» si la URL coincide con `sesion.url_sin_sesion` o si hay un enlace visible de `sesion.sin_sesion`. La usan:
  - `paso()`, antes de cada paso de una postulación;
  - `buscarCorreo()`;
  - `sesion()`, el sondeo cada 2 s de `vigilarInicioSesion` en `servicio.js`.
- `revisar(sel)` espera 1,5 s, llama a `sinSesion` y, si la marca `sesion.iniciada` está declarada, la espera 5 s con `ocultos: true`.

Los selectores llegan del servidor como datos. Cambiar un JSON corrige a todos los usuarios sin publicar otra extensión. Cambiar `motor.js` sí exige versión nueva.

Lo observado el 2026-10-15 con la sesión real del dueño:

| Página | Qué muestra |
|---|---|
| `www.magneto365.com/co`, HTML del servidor | Enlace «Iniciar sesión» a `web.magneto365.com/sign-in`; sin avatar ni `logoutBlock`; sin enlaces a `login.magneto365.com` |
| La misma página ya cargada | El enlace desaparece; aparece `[class*='logoutBlock_avatar']` con `img[alt='User Avatar']` |
| Correo de la cuenta | Fuera de los `<script>`, solo aparece en `[class*='mg_account_select'] … [class*='mg_tooltip_tooltip'] strong`, que está oculto |
| `web.magneto365.com/sign-in` con sesión | Redirige a `web.magneto365.com/profile/resume?callback=true` (cuerpo vacío por un momento) y luego a `www.magneto365.com/co/trabajos/buscar`, con avatar |

En el bot, `tarjeta.lineas(tj)` y `tarjeta.botones(tj, cb)` recorren todo `tj.cuentas`. `_datos_card` los copia en la card sin filtrar por `d.plataforma`.

## Goals / Non-Goals

**Goals:**
- Que el cambio de datos baste para que la extensión publicada (1.0.0) detecte la sesión de Magneto.
- Que el motor no vuelva a confundir un enlace de ingreso del HTML inicial con la falta de sesión en portales que declaran marca.

**Non-Goals:**
- Reconocer el formulario de postulación ni el perfil de Magneto con sesión.
- Cambiar cómo se detecta la sesión en Computrabajo.

## Decisions

### 1. Datos primero: magneto.json corrige el caso sin versión nueva
En `sesion`:
- `iniciada`: `["[class*='logoutBlock_avatar']", "img[alt='User Avatar']"]`;
- `sin_sesion`: queda solo el enlace «Ingresa a tu cuenta» a `login.magneto365.com`. Se quita `a[href*='web.magneto365.com/sign-in']`, porque está en el HTML inicial aunque haya sesión;
- `url_sin_sesion` no cambia.

Con la extensión 1.0.0:
- `revisar` ya no encuentra enlace de ingreso y espera la marca 5 s con `ocultos`;
- con sesión aparece el avatar y el resultado es «listo»;
- sin sesión no aparece y el resultado es `sin_marca_sesion`.

En `cuenta.correo` se agrega primero `[class*='mg_account_select'] [class*='tooltip'] strong`. `buscarCorreo` lo lee con `ocultos: true` y valida el formato, así que no se cuelan textos que no sean correos.

*Alternativa descartada:* que la marca prevalezca solo en el motor, conservando el enlace en `sin_sesion`. Obligaría a esperar la versión nueva de la extensión en cada navegador y la 1.0.0 seguiría fallando.

### 2. Motor: la marca prevalece y puede ser obligatoria
- `sinSesion(sel)`:
  - si la URL coincide con `url_sin_sesion`, devuelve «sin sesión» como hoy;
  - si hay marca `iniciada` presente, aunque esté oculta, devuelve «con sesión»;
  - si no, decide por el enlace de ingreso, como hoy;
  - con `sesion.marca_obligatoria: true`, la falta de marca también cuenta como sin sesión.
- Nueva función `esperarSesion(sel)`. Espera hasta `sesion.espera_ms` (por defecto 5000, como la espera actual de `revisar`) a que aparezca la marca y decide con `sinSesion`. Sale de inmediato si la URL es de ingreso, si ya hay marca o si el portal no declara marca. La usan:
  - `revisar`, en lugar de la secuencia «sinSesion y luego esperar la marca»;
  - `paso`. Con sesión, la marca ya está y sale de inmediato. Sin sesión, el primer paso termina en `sin_sesion` y el servicio corta el flujo, así que la espera no se repite en cada paso.
- `sesion()` (sondeo de la vigilancia) sigue siendo síncrona y usa el nuevo `sinSesion`. Con `marca_obligatoria`, la página intermedia vacía de `web.magneto365.com/profile/resume` ya no se toma como sesión iniciada. Así la pestaña no se cierra antes de tiempo.
- Magneto declara `marca_obligatoria: true` y `espera_ms: 10000`. La ventana minimizada frena los temporizadores y la página tarda más en cargarse.
- Computrabajo no declara `marca_obligatoria`, así que mantiene el comportamiento de hoy. Su marca `[data-info-user]` solo existe con sesión, y que prevalezca no cambia ningún caso conocido. Las pruebas actuales de Computrabajo lo confirman.

`manifest.json` sube a 1.1.0.

*Alternativa descartada:* esperar un tiempo fijo antes de cualquier detección. Retrasaría Computrabajo y no garantiza que la página haya terminado de cargarse.

### 3. Bot: bloque de conexión filtrado por plataforma
- `tarjeta.lineas(tj, solo=None, excepto=None)` y `tarjeta.botones(tj, cb, solo=None, excepto=None)`:
  - `solo=p` devuelve el navegador y la línea de `p`, o la línea pendiente de `p` si no tiene cuenta;
  - `excepto=p` devuelve las cuentas distintas de `p`;
  - sin argumentos, todo, como hoy.
- `_datos_card` pasa `solo=d.plataforma`.
- `_actualizar_tarjeta(usuario, cambiar, plataforma=None)`: los avisos de cuenta y los botones «cuenta» pasan su plataforma. Si hay card (`tj.pid`) y la plataforma no es la de esa postulación, el cambio se guarda en `tj.cuentas` igual que hoy. Pero en vez de repintar la card, se pinta o edita un **mensaje aparte** con `texto(tj, excepto=plataforma_de_la_card)` y sus botones. Su `mensaje_id` se guarda en kv `tarjeta_otros:{usuario}`.
- Al soltar la tarjeta (`_cerrar_card`, respaldo, alta terminada), también se borra `tarjeta_otros:{usuario}`.
- La plataforma de la card se lee de `postulaciones.plataforma`. Ya se consulta en `_datos_card`.

*Alternativa descartada:* mostrar en la card también los otros portales con acciones pendientes. Es justo lo que confundió al dueño: botones de Computrabajo en una vacante de Magneto.

## Risks / Trade-offs

- [Magneto cambia los nombres de sus clases (sufijos de módulos CSS)] → Los selectores usan `[class*='prefijo']` sin el sufijo, y la marca tiene dos alternativas (contenedor y `alt` de la imagen). Si deja de encontrarse, el portal sale como «sin sesión», el mismo síntoma de hoy y no algo peor.
- [La espera de 10 s alarga la revisión de Magneto sin sesión] → Solo cuando no hay sesión. La revisión corre en una ventana minimizada y no bloquea el popup.
- [El tooltip del correo no existe en otras cuentas, por ejemplo con un solo perfil] → `revisarPortal` ya sigue los enlaces «Mi cuenta» y `cuenta.urls`. Si no encuentra el correo, la card queda en «Buscando correo» y se reporta `pagina_correo` para fijarlo.
- [Mensaje aparte de conexión: un mensaje más en el chat] → Solo aparece si llega un aviso de otro portal con una card abierta, que es raro, y se edita en su sitio.

## Migration Plan

1. Desplegar en el Fedora: `git pull --ff-only` en `~/buscador-vacantes` y `systemctl --user restart buscador-asistente`. Los selectores nuevos llegan a la extensión publicada en su próximo latido.
2. Recargar la extensión 1.1.0 en el navegador del dueño y tocar ↻ en el popup: Magneto debe pasar a «Confírmala».
3. Vuelta atrás: revertir el commit y reiniciar el servicio. La 1.0.0 vuelve a recibir los selectores anteriores.
