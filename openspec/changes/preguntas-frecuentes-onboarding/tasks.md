# Tasks: Preguntas frecuentes en onboarding

## 1. Definición de preguntas y etiquetas

- [x] 1.1 🟢 Ligera: Agregar `semestre`, `enlace_portafolio` y `autorizacion_trabajo:colombia` a `CUESTIONARIO` en `buscador_vacantes/asistente/textos.py`.
- [x] 1.2 🟢 Ligera: Registrar las etiquetas correspondientes en `ETIQUETAS` en `buscador_vacantes/asistente/preguntas_tarjeta.py`.

## 2. Derivación automática desde la hoja de vida

- [x] 2.1 🟡 Media: Agregar campo `autorizacion_colombia` a `DatosLocales` y su detección en `enmascarar` en `buscador_vacantes/asistente/cv_lectura.py`.
- [x] 2.2 🟡 Media: Actualizar `derivar_del_cv` en `buscador_vacantes/asistente/conversacion.py` para precargar `semestre`, `enlace_portafolio` y `autorizacion_trabajo:colombia`.
- [x] 2.3 🟢 Ligera: Pasar `autorizacion_trabajo:colombia` en `locales` de `_leer_cv_exitoso` en `buscador_vacantes/asistente/conversacion.py`.

## 3. Pruebas y verificación

- [x] 3.1 🟡 Media: Agregar pruebas en `tests/asistente/test_preguntas_tarjeta.py`, `tests/asistente/test_cv_lectura.py` y `tests/asistente/test_bot.py` verificando que las preguntas presentes en el CV no se pregunten y las ausentes sí.
- [x] 3.2 🟢 Ligera: Ejecutar suite de pruebas con `.venv/Scripts/python -m pytest` y comprobar que pasen limpiamente.
