## Why

El 2026-10-28 a las 17:55 la tarjeta «Pregunta rápida (2 de 2)» de una vacante de Computrabajo llegó sin botones: «¿Cuentas con el aval por parte de tu institución educativa para iniciar proceso de prácticas de inmediato?» con solo «Escribe tu respuesta.». Tres causas se juntaron: Gemini estaba saturado entre las 17:56 y las 17:59 y el asistente se rindió a la primera falla y le pasó las preguntas al usuario; el portal dio la pregunta como campo de texto y la card solo pone botones cuando el portal trae opciones; y el aval es un dato del usuario que el asistente no recordaba como dato, solo como texto exacto de una pregunta.

## What Changes

- **IA saturada o sin contacto**: cuando el redactor o el clasificador de preguntas fallan por un problema temporal del proveedor, el servidor reintenta la resolución del formulario con esperas configurables (con latido del navegador mientras espera) antes de preguntarle al usuario. Sin clave de IA, con clave inválida, cuota o tope agotados no se reintenta: sigue como hoy.
- **Si los reintentos se agotan**: las preguntas pasan a la card como hoy, pero la card dice que la IA no respondió esta vez, para que el usuario sepa por qué se le pregunta.
- **Botones Sí/No en cualquier plataforma**: una pregunta pendiente sin opciones cuyo enunciado es claramente de sí o no («¿Cuentas con…?», «¿Tienes…?», «¿Puedes…?») muestra los botones «Sí» y «No» y «✍️ Escribir yo». Aplica a las preguntas del formulario de cualquier portal (Computrabajo, Magneto, elempleo, LinkedIn, motor genérico) y a los datos que pide el redactor sin sugerencias. Una pregunta que ya trae opciones del portal no cambia.
- **Aval de la institución como dato recordado**: nuevo campo `aval_institucion` del catálogo, con preguntas sembradas en el banco, que se guarda en el cuestionario del usuario al responderse y se usa solo en adelante, con cualquier redacción de la pregunta que el banco o la IA clasifique en ese campo.

Fuera de alcance: preguntar el aval en el alta (lo evalúa el change `preguntas-frecuentes-onboarding`), cambiar la extensión o los selectores, y un estado nuevo en la cola para «esperando a la IA».

## Capabilities

### New Capabilities

### Modified Capabilities

- `tarjeta-postulacion-asistente`: «Preguntas rápidas dentro de la card» incluye los botones Sí/No para preguntas de sí o no sin opciones del portal y el aviso de que la IA no respondió.
- `preguntas-encuesta-asistente`: «Respaldo sin IA» distingue la IA ausente de la IA caída y reintenta esta última; nuevo requisito del aval de la institución recordado.

## Impact

- Código: `buscador_vacantes/asistente/respuestas.py` (detector de sí/no, marca de falla temporal de IA en el contexto, `resolver` y `redactar_formulario`), `nucleo.py` (`resolver_formulario` con reintentos, `_crear_pendientes`), `tarjeta_postulacion.py` (texto y botones de la pregunta, aviso de IA), `conversacion.py` (`_texto_pendiente`, callback `pend`, pregunta sin card), `campos.py` (campo `aval_institucion`), `assets/asistente/banco_preguntas.yaml` (preguntas del aval), `buscador_vacantes/comun/config.py` y `config.yaml` (esperas de reintento).
- Pruebas: `tests/asistente/test_respuestas.py`, `test_campos.py`, `test_nucleo.py`, `test_tarjeta_postulacion.py`, `test_bot.py`, `tests/comun/test_config.py`.
- Sin cambios de esquema de base de datos ni de extensión: el tipo nuevo del pendiente es un texto más en `pendientes_usuario.tipo`.
- Despliegue: `git pull --ff-only` en el servidor y reinicio del servicio.
