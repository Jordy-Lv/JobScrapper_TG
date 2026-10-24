# Tasks

> Antes de empezar: revisar los specs contra la definición de «destacada» y de fecha que dejó la fase 2 (`visibilidad-area-y-fecha`).

## 1. Botón único y selector de vacantes (🟡)

- [ ] 1.1 Hacer que `NotificadorBotAPI.enviar_mensaje` acepte botones `url:`. En `publicacion.py`, reemplazar los botones por vacante por un solo botón URL `t.me/<bot>?start=l_<id_lote>`, con el texto del spec, y guardar el lote en `lotes_canal` solo al confirmarse el envío. Sin asistente activo, no hay botón. Verificar con los escenarios de «Un solo botón de postulación por mensaje del canal» y de «Lote de cada mensaje publicado» en `test_publicacion.py` y `test_notificador.py`.
- [ ] 1.2 Agregar `Indice.resolver_lote(id_lote, ahora)` en `asistente/vacantes.py`: lee `lotes_canal` en solo lectura, indexa las claves que falten y devuelve las vacantes en orden, o `None` si el lote venció. Verificar con pruebas en `tests/asistente/test_datos.py` o en un archivo nuevo `test_vacantes.py`.
- [ ] 1.3 Crear `asistente/selector.py`, con lógica pura: páginas de 6, texto numerado, ⭐ y ✅, y botones `sel:`, `selpag:` y `selx`. Su estado vive en `kv`. Verificar con pruebas unitarias del escenario «Lote de nueve vacantes» y de las marcas ⭐ y ✅.
- [ ] 1.4 Conectar el selector en la conversación:
  - `al_iniciar` reconoce `l_<id>`, guarda el lote pendiente durante el alta y lo muestra al terminarla;
  - `sel:` llama a `procesar_toque(..., origen="selector")`;
  - `pv:` y `v_` siguen funcionando.

  Si `dividir-conversacion-asistente` ya se aplicó, usar su registro `@boton`. Verificar con los escenarios de «El botón abre el bot en privado con el lote del mensaje», «Elegir una vacante sigue el flujo de postulación existente», «El lote sobrevive al registro» y «Compatibilidad con los botones ya publicados» en `tests/asistente/test_bot.py`.
- [ ] 1.5 Actualizar `asistente/textos.py` (`AYUDA`) y `docs/asistente/guia-usuario.md` con el botón único y el selector. Verificar que la guía describe el flujo tal como lo muestran las pruebas de 1.4.

## 2. Consultas desde el bot asistente (🔴)

> Tarea pesada: recomendar sesión nueva antes de empezarla y al terminarla.

- [ ] 2.1 Migrar `asistente.db` al esquema 3: columnas `ubicacion`, `modalidad`, `publicada`, `destacada` y `area` en `vacantes`. `Indice.indexar` las copia de `vistas`. Verificar en `tests/asistente/test_datos.py` la migración desde el esquema 2 y que una vacante indexada trae los datos nuevos.
- [ ] 2.2 Crear `asistente/consultas.py`, con lógica pura:
  - el dataclass `ConsultaVacantes`;
  - la validación pydantic con la lista cerrada de campos y valores;
  - la consulta SQL parametrizada sobre `vacantes`, ordenada con las destacadas primero y luego por fecha;
  - el alcance de los datos: solo el canal real, dentro de la retención y sin descartadas.

  Verificar con pruebas de cada filtro, de su combinación y de los escenarios «Vacante descartada» y «Sin resultados».
- [ ] 2.3 Implementar la tarjeta de filtros y los resultados en la conversación:
  - `/buscar` y el botón «🔎 Buscar vacantes»;
  - la tarjeta editable con el contador;
  - «Limpiar filtros» y el junior pausado;
  - los resultados con el selector de 1.3, en el modo `consulta`.

  Verificar con los escenarios de «Punto de entrada de las consultas», «Tarjeta de filtros con botones», «Nivel junior pausado en las consultas» y «Resultados paginados con postulación» en `test_bot.py`.
- [ ] 2.4 Implementar `/buscar <frase>`:
  - limpieza de la frase (200 caracteres, sin correos, teléfonos ni documentos);
  - llamada a DeepSeek con el cliente HTTP del radar y un prompt corto en `asistente.consultas.prompt_sistema`;
  - validación de la respuesta;
  - topes `ia_usuario_dia` (5) e `ia_servidor_dia` (200) contados en `asistente.db`;
  - búsqueda literal en el título y la empresa cuando no hay IA, con aviso.

  Verificar con respx los escenarios de «Búsqueda con las palabras del usuario», «Búsqueda por texto cuando la IA no está disponible» y «La frase del usuario no lleva datos personales a la IA».
- [ ] 2.5 Agregar `/buscar` a `AYUDA` y a `docs/asistente/guia-usuario.md`, con un aviso breve de que la frase se procesa con DeepSeek y sin datos personales. Verificar que la guía y `textos.py` coinciden.

## 3. Verificación en producción

- [ ] 3.1 👤 Desplegar en el Fedora (`git pull`, reinicio de `buscador-asistente`) y revisar el canal y el bot durante 3 días. Verificar que:
  - los mensajes tienen un solo botón y el selector funciona desde el móvil;
  - las destacadas aparecen marcadas con ⭐ en el selector;
  - `/buscar` responde con y sin IA.

## Workflow follow-up

- Archivar este change después de `crear-buscador-vacantes` y de `aprendizaje-primero-canal-y-consultas`: sus deltas usan `ADDED` sobre capacidades que nacen al archivarlos.
- Si `dividir-conversacion-asistente` se aplica antes del bloque 1, actualizar las rutas de las tareas 1.4 y 2.3 al paquete nuevo.
