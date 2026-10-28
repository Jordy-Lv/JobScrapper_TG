# Design: Preguntas frecuentes en onboarding

## Context

Durante el proceso de alta (onboarding) del asistente de Telegram, el usuario carga su hoja de vida en PDF. El asistente extrae los datos del documento y ejecuta `derivar_del_cv` para precargar respuestas en `cuestionario`. Posteriormente, en el paso `faltantes:0`, la función `_faltantes(usuario)` determina los índices de `t.CUESTIONARIO` que aún no tienen respuesta para presentarlos en una tarjeta interactiva única.

Hasta ahora, los campos `semestre`, `enlace_portafolio` y `autorizacion_trabajo:colombia` no formaban parte de `t.CUESTIONARIO`, y `derivar_del_cv` no los transfería desde el perfil extraído. Esto generaba formularios incompletos o preguntas repetidas durante la postulación.

## Goals / Non-Goals

**Goals:**
- Incluir `semestre`, `enlace_portafolio` y `autorizacion_trabajo:colombia` en `t.CUESTIONARIO` y en `pt.ETIQUETAS`.
- Derivar estos campos automáticamente desde la hoja de vida subida para que los usuarios cuyo CV ya contiene la información no tengan que responderlos manualmente.
- Mantener compatibilidad con la tarjeta de preguntas rápidas (botones por fila, opción "Omitir" en opcionales, respuesta libre de texto para portafolio).
- Preservar los índices y comportamiento de las pruebas existentes (en particular el índice 3 correspondiente a `documento`).

**Non-Goals:**
- Modificar el esquema de Gemini (`PerfilExtraido`) ni el prompt principal del LLM para extracción de CV: los campos de `formacion` (con `semestre`) y `enlaces` ya existen en `PerfilExtraido`, mientras que los datos de contacto y documentos sensibles se procesan localmente en `cv_lectura.py`.
- Cambiar la lógica del redactor con IA o del motor de formularios sin IA: ambos ya leen estos campos a través de `DatosUsuario.valor()`.

## Decisions

1. **Definición de items en `t.CUESTIONARIO`:**
   - `semestre`: `ItemCuestionario("semestre", "¿Qué semestre cursas?", ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Graduado"), por_fila=5, opcional=True)`. Ofrece selección rápida en teclado inline y botón para omitir si no aplica.
   - `enlace_portafolio`: `ItemCuestionario("enlace_portafolio", "Enlace a tu portafolio o GitHub (opcional)", opcional=True)`. Al no tener `opciones`, la tarjeta muestra el botón "Omitir" y espera un enlace escrito por el usuario.
   - `autorizacion_trabajo:colombia`: `ItemCuestionario("autorizacion_trabajo:colombia", "¿Tienes autorización para trabajar en Colombia?", ("Sí", "No"), por_fila=2)`. Respuesta binaria directa.
   - Ubicación: Se insertan después de `documento` (índice 3), manteniendo `actualizar_cv_portal` como la última pregunta de consentimiento del bloque.

2. **Detección y derivación del CV:**
   - `semestre`: `derivar_del_cv` toma el primer `semestre` no vacío de `perfil.formacion`.
   - `enlace_portafolio`: `derivar_del_cv` busca en `perfil.enlaces` los de tipo "github" o "portafolio", o aquellos cuya URL incluya `github.com`.
   - `autorizacion_trabajo:colombia`: `cv_lectura.py` inspecciona los datos locales y el texto del CV. Si detecta un documento de identidad colombiano (C.C., T.I., C.E.) o expresiones que confirmen autorización laboral/nacionalidad colombiana, se asigna `"Sí"` en `DatosLocales.autorizacion_colombia` y se pasa a `cuestionario["autorizacion_trabajo:colombia"]`.

3. **Filtrado en el onboarding:**
   - La función `_faltantes(usuario)` ya comprueba `not cuestionario.get(item.clave)`. Al poblarse en `derivar_del_cv`, cualquier dato que vino en el CV se excluye automáticamente de `_faltantes`, cumpliendo el requerimiento de que el bot solo pregunte lo que no venga en el CV.

## Risks / Trade-offs

- *Falsos positivos en autorización:* El uso de cédula colombiana (C.C./T.I.) o mención explícita es un indicador legalmente sólido de autorización laboral en Colombia. Para perfiles sin cédula colombiana en el CV, el bot pregunta directamente "Sí" o "No", lo que elimina ambigüedad.
