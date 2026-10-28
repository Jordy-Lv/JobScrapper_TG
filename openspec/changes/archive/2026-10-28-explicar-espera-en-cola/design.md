## Context

Ver proposal.md (Why). Estado actual que condiciona el diseño:

- `POST /latido` (`api.py`) recorre `cuerpo.portales`; para `sin_sesion` hace `continue` antes de actualizar `anteriores`, así que `navegadores.portales_json` solo guarda `{estado, cuenta}` de los portales con sesión y nunca el «sin sesión» ni su `motivo` (solo va al log).
- La extensión (`servicio.js`, `estadoPortales`) quita del latido los portales sin permiso de dominio (`tienePermiso`), y envía solo los que tienen selectores. Para el servidor, «habilitada con selectores y ausente del latido» equivale a «sin permiso».
- La asignación: `disponibles` = cuenta `ok`; `listos` = `disponibles` con estado `listo`; `cola.siguiente()` aplica «de a una por usuario», tope diario y pausa entre postulaciones; con `actualizar` (versión < `version_minima`) no se entrega trabajo. `config.plataformas[p].automatica` solo se mira al tocar «Postular» (`nucleo.camino_automatico`).
- `cola.vigilar()` corre cada minuto (`servicio.py`) y pasa `en_cola` → `esperando_navegador` cuando no hay latido en `navegador_caido_min`.
- La card (`tarjeta_postulacion.py`) es pura: `Card` en `kv` (`card:{pid}`) y `Datos` leídos de la base; la fase `en_cola` pinta un texto fijo. La conversación repinta con `_pintar_card`.
- La extensión en pausa (`ajustes().pausado`) sigue mandando latidos pero ignora el trabajo; el servidor no lo sabe.

## Goals / Non-Goals

**Goals:**
- Una sola fuente de verdad para «por qué no se asigna»: las mismas reglas que usa la asignación, sin duplicar umbrales.
- Diagnóstico genérico por plataforma, sin ramas por portal salvo datos (URL de ingreso, nombre del dominio).
- Cero ediciones de Telegram si la causa no cambió.

**Non-Goals:**
- No cambia el flujo de la extensión (`motor.js`, pasos, `ejecutar`) ni los selectores.
- No cambia la fase `sesion` (cuando el flujo ya corrió y el portal pidió sesión), ni `bloqueo`, ni el respaldo por plazos de `vigilar`.
- No detecta bloqueos que solo aparecen al abrir la vacante (correo sin verificar en el propio portal, `portal_cuenta_sin_verificar`): siguen en la fase `bloqueo`.
- No avisa con mensajes nuevos: solo edita la card existente.

## Decisions

**D1. Estado completo por portal en `portales_json`, sin migración.** Cada latido guarda por plataforma `{estado, motivo, cuenta, visto}`; `estado` puede ser `sin_sesion`, `incompleto`, `listo` o `sin_permiso` (plataforma con selectores ausente del latido). En `sin_sesion` se conserva el `cuenta` previo, que es el que se usa para no repetir avisos de cuenta. El correo nunca se guarda ahí. Se guardan también `version` (ya existe la columna) y `pausado` (dentro del JSON, clave `_pausado`, para no tocar el esquema). Alternativa descartada: tabla nueva por navegador y portal; más limpia pero exige migración y el JSON ya existe y es por navegador.

**D2. Módulo puro `espera.py`.** `causa(entrada) -> Causa | None`, con `Entrada` (plataforma de la postulación, navegadores vigentes con su latido, versión, pausa y portales; `version_minima`, `navegador_caido_min`, plataforma encendida y con selectores; restricción de la cola) y `Causa(codigo, plataforma, datos)`. El orden de prioridad del spec vive en una sola función. Con varios navegadores: si alguno no tiene causa, `None`; si no, la del latido más reciente. El núcleo arma la `Entrada` desde la base (`nucleo.espera(pid)`). Alternativa descartada: calcular la causa dentro del latido y guardarla por postulación; la causa depende de la hora (latido viejo, fin de la pausa) y de la cola, así que se calcula al pintar.

**D3. Restricciones de la cola compartidas.** Se extrae de `cola.siguiente()` una función `restriccion(usuario_id, plataforma, ahora) -> (codigo, cuando) | None` (`en_curso`, `tope_diario` con la medianoche de Bogotá, `pausa` con la hora de fin) que usan tanto `siguiente()` como el diagnóstico, para que la explicación nunca contradiga la asignación.

**D4. Plataforma apagada fuera de `disponibles`.** En el latido, una plataforma con `automatica = False` no entra en `disponibles` (tampoco para completar perfil). `cuentas` de la respuesta no cambia: la extensión lo sigue usando solo para revalidar el trabajo recibido. Alternativa descartada: solo explicar «apagada» sin dejar de asignar; el mensaje sería falso y la postulación se enviaría igual.

**D5. Campo `Card.espera`.** La card guarda `espera: {codigo, plataforma, datos} | None` (con valor por defecto, así las cards guardadas antes cargan igual). La fase sigue siendo `en_cola` o `esperando_navegador`; `_cuerpo` y `botones` usan `espera` cuando existe. Los textos van en `textos.ESPERAS` (plantillas con `{portal}`, `{dominio}`, `{version}`, `{minima}`, `{hora}`), y la URL de ingreso en `textos.URL_INGRESO` con respaldo en `URL_REGISTRO`. Para la cuenta se reutilizan los callbacks de `tarjeta.botones` (`cuenta:<plataforma>:si|no|nueva`); si la card ya trae `botones_conexion` (card dentro de la tarjeta del alta), no se duplican.

**D6. Disparadores y deduplicación.** Al final del latido, `nucleo.notificar({"tipo": "esperas", "usuario_id"})`; en `vigilar` (cada minuto) y tras `/plataformas on|off`, la conversación revisa las esperas de los usuarios con postulaciones en cola. `_revisar_esperas(usuario)` recorre sus postulaciones `postular` en `en_cola`/`esperando_navegador` con card, calcula la causa y solo si difiere de `card.espera` la guarda y llama a `_pintar_card`. Para que la hora de un «sin latido reciente» o el fin de una pausa no provoquen ediciones por minuto, `datos` solo incluye valores estables (hora del último latido, hora de fin), no cuentas regresivas.

**D7. `pausado` en el latido.** `Latido.pausado: bool | None = None`; `servicio.js` lo envía desde `ajustes()`. Es compatible hacia atrás: extensiones viejas no lo mandan y no se sube `version_minima`.

**D8. URL de ingreso por portal.** Computrabajo: `https://candidato.co.computrabajo.com/acceso/` (ya en sus selectores como `url_registro`); Magneto: `https://web.magneto365.com/sign-in` (enlace «Iniciar sesión» observado el 2026-10-05); elempleo: por confirmar en el reconocimiento, con respaldo en la portada (`URL_REGISTRO`). El dominio del permiso sale de `NOMBRES_PLATAFORMA`/una tabla `DOMINIOS` en `textos.py`.

## Risks / Trade-offs

- [La revisión de sesión de la extensión oscila entre «sin sesión» y «listo»] → la card editaría en cada cambio; se acepta porque cada edición refleja un cambio real y la deduplicación evita ediciones con la misma causa.
- [El estado del portal puede tener minutos de antigüedad (`REVISION_MAX_MS`)] → el mensaje describe el último reporte; cuando el usuario inicia sesión, la extensión ya fuerza un latido (`vigilarInicioSesion`), así que la card se corrige rápido.
- [Inferir «sin permiso» por ausencia] → también falta un portal recién habilitado que la extensión aún no revisó; se mitiga porque la extensión revisa las plataformas nuevas en el mismo latido y porque el texto solo pide activar el permiso, que es inocuo si ya está.
- [Más trabajo por latido (consultas por usuario cada 30 s)] → consultas indexadas por `usuario_id` sobre pocas filas; solo se tocan postulaciones en cola con card.
- [Límites de edición de Telegram] → solo se edita al cambiar la causa.

## Migration Plan

1. Desplegar el servidor en el Fedora: acepta `pausado` opcional y reescribe `portales_json` en el siguiente latido de cada navegador (sin migración).
2. Recargar la extensión para que envíe `pausado`; sin recargarla todo funciona salvo esa causa.
3. Reversión: volver al commit anterior; las claves nuevas de `portales_json` y de la card se ignoran.

## Open Questions

- URL exacta de ingreso de elempleo: se confirma en el reconocimiento del dueño; mientras tanto el botón abre la portada.
