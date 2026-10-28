## Context

Observado el 2026-10-18 en el Fedora (`data/asistente.db`) y en el Chrome del dueño:

- Postulación 54 (CEID Comfama, vacante que el dueño había aplicado y retirado): pasos `aplicar`, `preguntas` (9 s sin encontrar el contenedor, es `opcional`), `enviar`, `confirmar` (25 s) y `incierta`. La evidencia es la vacante con «Aplicar» y el indicador de carga, sin encuesta ni banner. La página de la vacante carga normal; no se sabe por qué Magneto no responde al reaplicar (hipótesis: la vacante retirada).
- Postulación 55 (Mosquera, vacante nueva): `preguntas` empezó a las 07:27:32, el servidor guardó las 9 respuestas (6 abiertas, 3 de botones; 2 redactadas por la IA) y nunca hubo `llenado`; a las 07:29:38 la cola la marcó `navegador_cerrado`, 2 min 6 s después de esa última señal.
- Prueba en vivo en la misma vacante: la encuesta sale 2 s después de «Aplicar», `leerPreguntas` encuentra los 9 bloques y el llenado con el mismo método de `asignarValor` deja todo aceptado y «Enviar respuestas» habilitado. El motor y los selectores no son la causa.
- El latido que vigila la cola (`navegadores.ultimo_latido`) se refresca en `postulacion_de` al empezar cada llamada de la postulación. `navegador_caido_min` vale 2. Una llamada que tarda más de 2 min (la IA con reintentos, el CV adaptado) deja pasar el plazo sin otra señal, y `cola.vigilar` marca `navegador_cerrado`; con `envio_pulsado=1` (se pone en `aplicar`) queda `incierta` y nunca se reintenta.
- El servidor no registra cuánto tarda cada llamada, así que la causa de la 55 sigue siendo una hipótesis: el plan incluye medirla.

## Goals / Non-Goals

**Goals:**
- Que una llamada larga del servidor no deje la postulación como `navegador_cerrado` mientras se resuelve.
- Que «Aplicar» sin respuesta del portal se distinga de «enviado sin confirmación» y se pueda reintentar.
- Que un llenado que se corta deje en el historial hasta qué pregunta llegó, y que el servidor registre cuánto tardó resolver el formulario.

**Non-Goals:**
- Arreglar por qué Magneto no responde al reaplicar una vacante retirada.
- Cambiar el plazo `navegador_caido_min` ni el modelo de latidos de la extensión.
- Tocar el flujo de otros portales más allá de lo que comparte `motor.js` y la cola.

## Decisions

1. **Latido durante el formulario, en el servidor.** `formulario` (api.py) corre `resolver_formulario` como tarea y, mientras no termina, refresca `ultimo_latido` del navegador cada 30 s; al terminar, una vez más. Alternativa descartada: que la extensión mande latidos paralelos, porque el latido es el que ejecuta el trabajo (`enCurso`) y un segundo canal complica el service worker. Alternativa descartada: subir `navegador_caido_min`, porque retrasa también el aviso de un navegador realmente caído.
2. **Medir antes de afirmar.** `formulario` registra el tiempo de `resolver_formulario` como paso de la postulación (`formulario_resuelto`, con segundos). Así la próxima falla confirma o descarta la hipótesis.
3. **«Aplicar» sin respuesta, en el paso `confirmar`.** `magneto.json` declara en `confirmar` un nuevo campo `sin_efecto` con el botón `button[class*='applyButton_apply-btn']` y el motor lo usa como `no_enviado`: al vencer `ms` sin confirmación, si ese botón sigue y no hay preguntas, devuelve error con motivo `aplicar_sin_efecto`. Con el modal ausente y el botón «Aplicar» presente nada se envió, a diferencia de la encuesta visible, que ya tiene su propio error. Los casos `ya_postulado` y `cerrada` se siguen evaluando antes.
4. **Motivo propio y card.** El motor reporta `formulario_desconocido` con el motivo `aplicar_sin_efecto`. El servidor, al recibir ese motivo, lo guarda tal cual; `textos.py` suma el texto «el portal no cargó la postulación; no se envió nada» y la card lo muestra con «Reintentar» en lugar de «el formulario del portal cambió». Alternativa descartada: un estado nuevo en `cola.py`, por el costo de migración para un caso que cabe en un motivo.
5. **Registro por respuesta.** `llenar` devuelve la lista de respuestas escritas y `servicio.js` reporta un paso `llenado_N` por cada una, sin su texto (privacidad: el texto ya está en la tabla `respuestas`). Una pregunta de 9 genera 9 pasos; el tope de 80 campos de `leerPreguntas` acota el volumen.

6. **Tope al llenado.** Hoy `formulario()` en `servicio.js` ejecuta `llenar` con `enPestana` sin límite (a diferencia de los demás pasos, que pasan por `correrSeguro`). En la 55 la extensión no leyó cuentas entre las 02:27:20 y las 02:30:22, es decir, el flujo estuvo ocupado unos 3 minutos dentro de la extensión, no esperando al servidor (la IA tardó unos 13 s en la 58). `llenar` se corre con `Promise.race` y un tope de 30 s; al vencer, la postulación termina con el motivo `llenado_sin_respuesta`, que la card trata como `aplicar_sin_efecto` (no se envió nada, «Reintentar»). Si `envio_pulsado` ya estaba en 1 por el paso `aplicar`, el reintento lo reinicia como hace hoy `cola.reintentar`.
7. **El latido del servidor pasa a mejora secundaria.** La 58 mostró que resolver el formulario con IA tarda ~13 s, así que la hipótesis de las llamadas de más de 2 min es poco probable. Se mantiene por barato, junto con la medición `formulario_resuelto`, pero no se espera que corrija la 55.

## Risks / Trade-offs

- «Reintentar» pone `envio_pulsado=0`: si «Aplicar» en realidad sí envió y la página no lo mostró, un reintento duplicaría la postulación. Se mitiga exigiendo que el botón siga presente y sin banner «Ya aplicaste» al fallar, y el reintento vuelve a pasar por `ya_postulado`.
- Si la hipótesis del latido es falsa, el arreglo 1 no corrige la 55; el paso `formulario_resuelto` y los `llenado_N` lo mostrarán en la siguiente falla, por eso entran en este mismo change.
- Un latido forzado puede ocultar una llamada realmente colgada: se acota con el tiempo máximo de la IA (`timeout_s`) y el plazo total de ejecución de la cola.
