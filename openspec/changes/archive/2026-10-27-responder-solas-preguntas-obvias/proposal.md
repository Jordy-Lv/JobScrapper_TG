## Why

La encuesta de Magneto trae preguntas de Sí/No cuya respuesta es obvia porque el usuario ya está postulando: «¿Te animas a dar el siguiente paso en tu camino laboral y participar en este proceso que podría abrirte nuevas oportunidades?» o «¿Confirmas tu participación en el proceso?». Hoy solo se responden solas si hay IA y ella elige la opción (`_redactar` en `nucleo.py`); sin clave de IA, en nivel Ahorro, o si la IA devuelve «faltan datos», caen a la card como «Pregunta rápida (2 de 2)» y la postulación espera al usuario por algo que nunca va a contestar «No».

## What Changes

- Nueva regla determinista en `resolver()` (`respuestas.py`), **sin IA**: una pregunta con opciones que pide confirmar interés o participación en el proceso, la vacante o la postulación se resuelve eligiendo la opción afirmativa («Si», «Sí», «Yes»).
- La regla es estrecha: exige a la vez una fórmula de interés o confirmación («te animas», «confirmas», «estás interesado», «deseas continuar»…) y una referencia al proceso, la vacante o la postulación, más una opción afirmativa y una negativa claras.
- No cambia el orden de prioridad: lo que el usuario respondió o aprendió manda sobre la regla, y las autorizaciones y aceptaciones (tratamiento de datos, términos, consentimiento) siguen yendo siempre a la card, antes de evaluar la regla.
- La respuesta queda con origen `perfil`, por lo que aparece en el resumen «Tus respuestas» sin 🤖 ni 💬 nuevos.
- Pruebas en `tests/asistente/test_respuestas.py` y ajuste del escenario de Magneto del spec.

No cambia: la extensión, `magneto.json`, el redactor ni el banco de preguntas.

## Capabilities

### New Capabilities
<!-- Ninguna -->

### Modified Capabilities
- `preguntas-encuesta-asistente`: la confirmación de interés o participación se responde sola sin depender de la IA; el requisito «Opciones elegidas en la misma llamada» deja de cubrir ese caso.

## Impact

- `buscador_vacantes/asistente/respuestas.py` (`resolver`, patrón y función nuevos).
- `tests/asistente/test_respuestas.py`.
- `openspec/specs/preguntas-encuesta-asistente/spec.md` (al archivar).
- Despliegue: `git pull` en el Fedora y reiniciar el servicio; la extensión no cambia.
