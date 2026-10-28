## Why

El 2026-10-18 dos postulaciones de Magneto terminaron como «incierta» sin enviarse y sin decir por qué. La 54 (CEID Comfama, vacante aplicada y luego retirada) se quedó con el spinner tras «Aplicar» y sin encuesta, y la card dijo «Magneto no mostró la confirmación» aunque no se envió nada. La 55 (práctica de Mosquera) leyó la encuesta de 9 preguntas y el servidor armó las respuestas, pero nunca hubo paso `llenado` y a los 2 minutos la cola la marcó `navegador_cerrado`. En vivo se comprobó que el llenado en la página funciona y que «Enviar respuestas» se habilita: el fallo está en cómo se vigila y se reporta el flujo, no en los selectores.

## What Changes

- El servidor mantiene vivo el latido del navegador mientras resuelve un formulario largo (la IA, el CV adaptado): hoy el latido se refresca solo al empezar cada llamada, y una llamada de más de `navegador_caido_min` (2 min) deja la postulación como `navegador_cerrado` aunque siga trabajando. Es una causa probable de la 55, no probada.
- Si tras «Aplicar» Magneto no muestra ni la encuesta ni el modal de confirmación y la vacante sigue con su botón «Aplicar», la postulación termina con un motivo propio («Magneto no procesó “Aplicar”: no cargó la encuesta ni confirmó») en vez de «no mostró la confirmación».
- La extensión reporta al servidor cada respuesta que escribe o marca (`llenado_n`), para ver hasta dónde llegó un llenado que se corta.
- Los selectores de Magneto suben de versión con el indicador del botón «Aplicar» como señal de «no se envió».

## Capabilities

### New Capabilities

### Modified Capabilities
- `postulacion-magneto`: requisito de confirmación (distinguir «no se procesó Aplicar» de «sin confirmación») y requisito de respuesta de la encuesta (registro de cada respuesta llenada).
- `tarjeta-postulacion-asistente`: la card de una postulación que no se procesó dice que Magneto no cargó la encuesta y que no se envió nada, en vez del aviso de confirmación ausente.

## Impact

- Servidor: `buscador_vacantes/asistente/api.py` (latido durante `/formulario`), posible ajuste en `cola.py`.
- Extensión: `extension/motor.js` (`llenar`, `confirmar`) y `extension/servicio.js` (`reportar` por respuesta).
- Datos: `assets/asistente/selectores/magneto.json` (versión 2026.10.18-2).
- Texto: `buscador_vacantes/asistente/textos.py` y la card en `tarjeta_postulacion.py`.
- Pruebas: `tests/asistente/test_extension.py`, `test_api.py` / `test_cola.py`, `test_tarjeta_postulacion.py`.
- Despliegue: pull en el Fedora, reinicio del servicio y recarga de la extensión en el Chrome del dueño.
