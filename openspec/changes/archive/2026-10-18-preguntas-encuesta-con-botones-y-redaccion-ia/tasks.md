## 1. Esquema y configuración

- [x] 1.1 Migración v4 en `datos.py` (decisión 9): columnas `pendientes_usuario.tipo`, `preferencias_portal.revisar_respuestas`, `respuestas.pregunta_norm` y `respuestas.estado`, índice único, relleno de `pregunta_norm` y borrado del banco con origen `ia`. Verificar en `tests/asistente/test_datos.py` con una base v3 que conserve las entradas sembradas y que pierda las de IA
- [x] 1.2 Actualizar en `config.yaml` el modelo, la temperatura y `max_tokens` de la tarea `responder` en cada proveedor (decisión 3). Verificar que la configuración carga y que las pruebas de `tests/comun/test_config.py` siguen en verde

## 2. Clasificación y redactor (respuestas.py)

- [x] 2.1 Sumar `formato` a `Clasificacion` y guardar `redactar` en el banco para preguntas compuestas o de prosa (decisión 1). Verificar en `tests/asistente/test_respuestas.py` con el caso de programa e institución y con un dato simple
- [x] 2.2 Implementar `redactar_formulario` con el esquema `RedaccionFormulario` y la instrucción nueva, con datos aprendidos, el dato reservado y `maximo` (decisiones 2, 4 y 6). Verificar con IA simulada: pregunta compuesta, varias preguntas en una llamada, dato faltante con sugerencias, dato reservado, respuesta fuera de índice ignorada y falla de IA
- [x] 2.3 Añadir `recortar_a_limite` y aplicarlo a cada redacción con `maximo`. Verificar los cortes en punto, en espacio y sin límite
- [x] 2.4 Quitar `_redactar` por pregunta y su uso en `resolver`: una pregunta `redactar` queda marcada para el redactor por formulario. Verificar que las preguntas con opciones y los datos simples no llaman al redactor

## 3. Núcleo y API

- [x] 3.1 Reescribir `resolver_formulario` en dos fases, con reutilización de redacciones por postulación y `_guardar_respuestas` con upsert (decisiones 2 y 7). Verificar en `tests/asistente/test_nucleo.py`: una sola llamada para varias preguntas, segunda pasada que redacta solo lo que faltaba, y sin IA las preguntas de texto como pendientes `formulario`
- [x] 3.2 Crear pendientes de tipo `dato` con sugerencias, deduplicados por `pregunta_norm`, y hacer que `responder_pendiente` guarde el dato corto, incluido `__reservado__` (decisiones 5 y 6). Verificar que la postulación se reencola y que, en la siguiente pasada, el dato llega al redactor y no se vuelve a preguntar
- [x] 3.3 Sumar `Campo.maximo` y `Pregunta.maximo` en `api.py` y la preferencia `revisar_respuestas` en `preferencias.py` y los endpoints `/preferencias`. Verificar en `tests/asistente/test_api.py`

## 4. Card: datos faltantes y revisión

- [x] 4.1 En `tarjeta_postulacion.py`, pintar los pendientes `dato` con un botón por sugerencia, «✍️ Escribir yo» y «Prefiero no decirlo», y los `formulario` como hoy. Verificar en `tests/asistente/test_tarjeta_postulacion.py`
- [x] 4.2 En `conversacion.py`, manejar los toques de sugerencia, escribir y reservado, con la espera de texto solo tras «Escribir yo» cuando hay sugerencias y el borrado del texto escrito. Verificar en `tests/asistente/test_bot.py` los tres caminos y sin IA
- [x] 4.3 Implementar el modo revisión (decisión 8): `esperar_usuario` con respuestas `propuesta`, aviso `revision_respuestas`, fase `REVISION` con «✅ Enviar» y «✏️ Corregir», corrección con origen `usuario` y reanudación que reutiliza lo aprobado. Verificar en `test_nucleo.py`, `test_tarjeta_postulacion.py` y `test_bot.py`: revisión encendida, apagada, formulario sin redacciones y corrección
- [x] 4.4 Revisar que `resumen_postulacion.py` marque 🤖 en lo redactado y 💬 en lo corregido o escrito tal cual, y que nunca muestre `__reservado__`. Verificar en `tests/asistente/test_resumen_postulacion.py`

## 5. Extensión (después de cerrar `magneto-confirmar-y-leer-encuesta`)

- [x] 5.1 En `motor.js`, enviar `maximo` leído de `maxlength` en cada campo de texto. Verificar en `tests/asistente/test_extension.py` con un fixture que tenga `maxlength`
- [x] 5.2 En `popup.html` y `popup.js`, añadir el interruptor «Revisar respuestas antes de enviar» en la vista del portal, guardado con `preferenciasGuardar`. Verificar en `tests/asistente/test_extension.py`

## 7. Opciones en la misma llamada (Magneto y elempleo)

- [x] 7.1 En `respuestas.py`, mandar al redactor las preguntas con opciones sin dato conocido, con sus opciones numeradas, y aceptar solo una `opcion` válida (decisión 11). Verificar en `tests/asistente/test_respuestas.py`: opción elegida, opción fuera de rango y consentimiento sin IA
- [x] 7.2 En `nucleo.py`, convertir la opción elegida en respuesta de origen `ia`, reutilizarla en la segunda pasada y mandar a la card las inválidas; en `conversacion.py`, lo mismo para las preguntas pegadas. Verificar en `tests/asistente/test_nucleo.py` con la encuesta de Magneto y el cuestionario de elempleo

## 6. Cierre

- [x] 6.1 Ejecutar toda la suite de `tests/` y `ruff`, y verificar que quedan en verde
- [x] 6.2 👤 Del dueño: reiniciar `buscador-asistente` en Fedora y recargar la extensión. Postular en Computrabajo a una vacante con preguntas abiertas y verificar la pregunta compuesta completa, la pregunta de dato en la card y 🤖 en «Tus respuestas». Repetir con la revisión encendida en ese portal — Hecho el 2026-10-18 en elempleo (postulación 46: dos respuestas redactadas completas con 🤖 y una del perfil; la 48 no traía cuestionario). Computrabajo y la revisión encendida no se probaron con una postulación real; el dueño pidió cerrar.
