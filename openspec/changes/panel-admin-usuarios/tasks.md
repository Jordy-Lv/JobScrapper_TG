## 1. Grupo y membresía

- [ ] 1.1 🟡 Esquema 5 de `asistente.db`: tabla `eventos_grupo`, su limpieza por `retencion_dias` y `kv.panel_grupo_desde`. Verificar con una prueba de migración en `tests/asistente/test_datos.py`.
- [ ] 1.2 🟡 `Comprobador.aplicar_aviso` en `membresia.py`: entrada o salida, suspender o reactivar al usuario del bot y registrar el evento sin datos de quien no es usuario. Verificar con pruebas en `tests/asistente/test_membresia.py` (sale, vuelve, no usuario, otro chat, aviso repetido).
- [ ] 1.3 🟢 `ChatMemberHandler` del grupo en `bot.py`. Verificar con una prueba en `tests/asistente/test_bot.py` que solo atiende el chat del grupo.
- [ ] 1.4 🟡 Conteo de miembros (`getChatMemberCount` con caché) y entradas, salidas y miembros por día en `metricas_dia_asistente`. Verificar con pruebas del resumen.

## 2. Datos del panel

- [ ] 2.1 🟡 `panel/consultas_usuarios.py`: tabla paginada con búsqueda, filtros y orden, ficha y embudo de altas, con una lista blanca de columnas. Verificar con pruebas, incluida una que recorre las claves del JSON y falla si aparece un campo personal.
- [ ] 2.2 🟡 Endpoints GET `/panel/datos/usuarios`, `/usuarios/{id}`, `/grupo` y `/postulaciones`, y POST `/usuarios/{id}/suspender` y `/reactivar` con CSRF, 409 y auditoría. Verificar con pruebas en `tests/asistente/test_panel_usuarios.py`.
- [ ] 2.3 🟡 Postulaciones: totales desde el resumen, y motivos de fallo, mediana de duración y tabla en vivo, con el aviso fuera de la retención. Verificar con pruebas de la tasa de éxito y de la mediana.

## 3. Página

- [ ] 3.1 🔴 Secciones Usuarios (tabla, ficha, diálogo de confirmación, embudo), Grupo y Postulaciones en `assets/asistente/panel/`. Verificar en el navegador del panel de vista previa con datos de prueba, en escritorio y a 375 px, que suspender pide confirmación y actualiza la fila.

## 4. Documentación y despliegue

- [ ] 4.1 🟢 Actualizar la documentación del panel en `docs/asistente/` con las vistas nuevas y el alcance del registro del grupo. Verificar que los enlaces existen.
- [ ] 4.2 👤 En el Fedora: desplegar, salir y volver al grupo con una cuenta de prueba, y comprobar la suspensión y reactivación en el acto y los conteos en la vista Grupo. Verificar con una captura.
