# Proposal: Preguntas frecuentes en onboarding

## Why

Los formularios de postulación suelen requerir con frecuencia información académica y legal común: el semestre actual cursado, un enlace a portafolio o perfil de GitHub, y la confirmación de autorización para trabajar en Colombia. Si bien estos campos existen en el catálogo técnico (`CAMPOS` y `CAMPOS_PARAMETRO`), no estaban incluidos en el cuestionario base de Telegram (`CUESTIONARIO`) ni se derivaban automáticamente de la hoja de vida subida en el alta.

Como consecuencia, durante el alta no se recolectaban y, al postular a vacantes que los exigían, el asistente debía detenerse a solicitarlos o quedaban sin resolver.

## What Changes

- Se agregan las preguntas frecuentes al cuestionario base de Telegram (`CUESTIONARIO` en `buscador_vacantes/asistente/textos.py`):
  - `semestre`: "¿Qué semestre cursas?" con botones del 1 al 10 y opción "Graduado" (opcional).
  - `enlace_portafolio`: "Enlace a tu portafolio o GitHub (opcional)" como campo abierto de texto con botón "Omitir".
  - `autorizacion_trabajo:colombia`: "¿Tienes autorización para trabajar en Colombia?" con botones "Sí" y "No".
- Se registran sus etiquetas en `ETIQUETAS` (`buscador_vacantes/asistente/preguntas_tarjeta.py`).
- Se amplía `derivar_del_cv` y la lectura de CV (`cv_lectura.py` y `conversacion.py`) para extraer estos datos directamente del CV cuando estén disponibles:
  - `semestre`: a partir de la formación académica (`perfil.formacion[0].semestre`).
  - `enlace_portafolio`: a partir de los enlaces del perfil de tipo "github" o "portafolio", o URLs correspondientes.
  - `autorizacion_trabajo:colombia`: se infiere como "Sí" si en el documento de identidad local o en el texto del CV se detecta un documento colombiano (C.C., T.I., C.E.) o declaración explícita de autorización/nacionalidad.
- El asistente en Telegram solo formula durante el onboarding (`_faltantes`) las preguntas del cuestionario que no hayan sido resueltas por el CV ni contestadas previamente.

## Capabilities

### Modified Capabilities

- `preguntas-rapidas-asistente`: se amplía la cobertura del cuestionario del alta para incluir semestre, enlace de portafolio y autorización laboral en Colombia, omitiéndolos cuando el CV los responde.

## Impact

- Código:
  - `buscador_vacantes/asistente/textos.py`: definición de los nuevos items en `CUESTIONARIO`.
  - `buscador_vacantes/asistente/preguntas_tarjeta.py`: etiquetas legibles para resumen y edición.
  - `buscador_vacantes/asistente/cv_lectura.py`: detección en locales de documentos y autorización en Colombia.
  - `buscador_vacantes/asistente/conversacion.py`: derivación de semestre, portafolio y autorización en `derivar_del_cv`.
- Pruebas:
  - `tests/asistente/test_preguntas_tarjeta.py`: etiquetas y tarjeta única.
  - `tests/asistente/test_cv_lectura.py`: detección de autorización de trabajo colombiana.
  - `tests/asistente/test_bot.py`: omisión de preguntas ya derivadas del CV y presencia de las faltantes.
