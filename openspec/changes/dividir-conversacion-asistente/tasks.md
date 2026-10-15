## 1. Precondiciones

- [ ] 1.1 👤 El dueño confirma que el piloto del asistente está estable (sin errores abiertos en el log de `buscador-asistente`) y que ninguna otra sesión trabaja sobre `asistente/conversacion.py`. Verificar con su respuesta anotada aquí.
- [ ] 1.2 👤 El dueño confirma el orden de la decisión 6 del `design.md`: este change va antes de `preguntas-encuesta-con-botones-y-redaccion-ia` y `reenviar-tarjeta-preguntas-al-retomar-alta`. Verificar con su respuesta anotada aquí.
- [ ] 1.3 🟢 Crear la rama `dividir-conversacion-asistente` desde `main`. Anotar la línea base de la suite y `ruff check`, y congelar la lista de métodos de `Conversacion` (`dir(Conversacion)`) para la prueba de la tarea 4.3. Verificar con los números y la lista anotados aquí.

## 2. Caracterización (antes de mover)

- [ ] 2.1 🟡 Fijar el reparto exacto método por método y prefijo por prefijo, leyendo el código, y actualizar la tabla de la decisión 1 del `design.md` si cambia. Confirmar si `alta` tiene productor. Verificar con la tabla completa: cada método de `Conversacion` y cada caso de `al_boton` tiene módulo.
- [ ] 2.2 🟡 Medir la cobertura de `conversacion.py` (comando en la decisión 3). Verificar con el informe guardado aquí: líneas sin cubrir por caso de `al_boton` y por rama de `al_texto`.
- [ ] 2.3 🔴 Escribir pruebas de caracterización en `tests/asistente/test_bot.py` para cada caso de `al_boton` y cada rama de `al_texto` sin cubrir. Cada prueba fija los mensajes, botones y estados que produce hoy. Verificar con las pruebas en verde sobre el código **sin mover** y con una cobertura de `al_boton` del 100 % por caso.
- [ ] 2.4 🟢 Commit «Pruebas de caracterización de la conversación del bot». Verificar con `test_bot.py` en verde y `ruff check` limpio.

## 3. Movimiento

- [ ] 3.1 🟡 `git mv buscador_vacantes/asistente/conversacion.py buscador_vacantes/asistente/conversacion/principal.py` y crear `__init__.py`, que reexporta `Conversacion`, `Bloqueado`, `Botones`, `Salida`, `RespuestaToque`, `Opciones`, `cb` y `botones_proveedores`. Verificar con `test_bot.py`, `test_servicio.py` y la prueba de arquitectura en verde sin tocar imports externos, y con `git log --follow` de `principal.py`.
- [ ] 3.2 🟡 Extraer `base.py` (tipos, `ConversacionBase.__init__` y utilidades). Verificar con `test_bot.py` en verde.
- [ ] 3.3 🔴 Extraer los flujos en este orden, uno por commit, moviendo el código sin reescribirlo: `avisos`, `comandos`, `postulacion`, `tarjetas`, `cuestionario`, `perfil` y `alta`. Verificar con `test_bot.py` en verde tras cada commit.
- [ ] 3.4 🔴 Registro de botones (decisión 2): crear el decorador `boton` y pasar cada caso del `match` a `_b_<prefijo>` en su módulo, con el mismo cuerpo. `al_boton` queda como despachador corto. Verificar con `test_bot.py` en verde, pruebas de prefijo desconocido y de prefijo repetido (`ValueError` al importar), y la revisión de los usos de `tid`, `data`, `partes` y `ahora` anotada aquí.

## 4. Pruebas de estructura

- [ ] 4.1 🟡 `tests/asistente/test_conversacion_estructura.py`: registro completo con `ast` (cada `cb("…")` tiene manejador, y los manejadores sin productor están en `HEREDADOS` con su motivo). Verificar con la prueba en verde y con que falla al borrar un manejador o al agregar un `cb("nuevo")` sin manejador.
- [ ] 4.2 🟢 Pruebas de tamaño (500 líneas o menos por módulo), de límites (los flujos no se importan entre sí) y de estado (solo `ConversacionBase` define `__init__`). Verificar con las pruebas en verde y con que fallan ante una violación a propósito.
- [ ] 4.3 🟢 Prueba de interfaz: `dir(Conversacion)` contiene la lista congelada en la tarea 1.3, más los `_b_*` nuevos. Verificar con la prueba en verde.

## 5. Verificación

- [ ] 5.1 🟡 Suite completa y `ruff check` / `ruff format --check`. La suite tarda unos 11 minutos: lanzarla en segundo plano y no tocar archivos mientras corre. Verificar con el mismo resultado que la línea base, más las pruebas nuevas.
- [ ] 5.2 🟡 `uv run buscador.py asistente servicio` en local sin red real: arranca, procesa una tarea periódica y se detiene limpio. Verificar con el log.
- [ ] 5.3 🟢 Actualizar la sección «Consecuencias» del ADR `docs/decisiones/0001-paquetes-comun-radar-asistente.md` (la división ya está hecha) o crear un ADR 0002 con las decisiones 1 y 2. Verificar leyendo el documento.

## 6. Planes abiertos

- [ ] 6.1 🟢 Actualizar las referencias a `conversacion.py` y a sus métodos en los planes de `preguntas-encuesta-con-botones-y-redaccion-ia`, `reenviar-tarjeta-preguntas-al-retomar-alta` e `ia-multiproveedor-asistente`, con el módulo nuevo de cada método y sin tocar tareas ya marcadas. Verificar con `grep -rn "conversacion.py" openspec/changes` sin referencias viejas en changes abiertos.

## 7. Cierre (👤)

- [ ] 7.1 👤 El dueño confirma unir a `main` y desplegar. Verificar con su respuesta.
- [ ] 7.2 👤 `git pull --ff-only` en el Fedora, reinicio de `buscador-asistente` y prueba manual: `/start`, un ⚡ del canal, un botón de la card y `/estado`. Verificar con el servicio activo sin reinicios y las respuestas iguales a las de antes. Actualizar la memoria del plan de reestructura (fase 3 hecha).
