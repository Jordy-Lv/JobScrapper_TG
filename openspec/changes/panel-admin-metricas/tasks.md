## 1. Configuración y esquema

- [ ] 1.1 🟢 Agregar el modelo `AsistentePanel` (activo, admins, enlace_min, sesion_h, dias_metricas, tipos) a `comun/config.py` y la sección `asistente.panel` a `config.yaml`, con `activo: false` y los tipos de D6. Verificar con pruebas en `tests/comun/test_config.py`, incluido el error con `activo: true` sin `url_publica`.
- [ ] 1.2 🟡 Esquema 4 de `vacantes.db`: tabla `metricas_dia` y su limpieza por `dias_metricas` en `Estado.limpiar`. Verificar con una prueba de migración desde el esquema 3 y otra de limpieza.
- [ ] 1.3 🟡 Esquema 4 de `asistente.db`: tablas `panel_sesiones` (hash, tipo enlace o sesión, telegram_id, csrf, creado, vence, usado, ultimo_uso) y `metricas_dia_asistente`. Verificar con una prueba de migración en `tests/asistente/test_datos.py`.

## 2. Métricas históricas

- [ ] 2.1 🟡 `comun/metricas.py`: `tipo_de(titulo, tipos)` con la normalización de `radar/filtros.py`. Verificar con pruebas de aprendiz SENA, trainee, intern, junior, otro y del orden de prioridad.
- [ ] 2.2 🔴 `resumir_dia` del radar (vistas, publicadas, corridas, descartes por regla, IA por tarea, por las dimensiones de D4), idempotente, y la llamada en `radar/corrida.py` para hoy y ayer antes de `limpiar`. Verificar con pruebas: recalcular dos veces da lo mismo, cuadra con `vistas`, día que cruza la medianoche, y el resumen sobrevive a la limpieza.
- [ ] 2.3 🟡 Relleno inicial al migrar al esquema 4: resumir todos los días con detalle. Verificar con una prueba con 90 días de `vistas` y 30 de `corridas`.
- [ ] 2.4 🟡 Resumen diario del asistente en `tareas_periodicas` (cada hora, hoy y ayer), sin ids de usuario. Verificar con pruebas en `tests/asistente/test_servicio.py`.

## 3. Acceso al panel

- [ ] 3.1 🟡 `asistente/panel/sesiones.py`: crear enlace, canjearlo (de un solo uso, en una transacción), validar la sesión, cerrarla y validar el CSRF, guardando solo hashes. Verificar con pruebas de enlace vencido, usado dos veces, sesión vencida, admin retirado y cierre.
- [ ] 3.2 🟡 Comando `/panel` en `Conversacion`: solo admins y solo por chat privado, con mensaje efímero que vence con el enlace y respuesta de comando desconocido para los demás. Verificar con pruebas en `tests/asistente/test_bot.py`.
- [ ] 3.3 🟡 Router `/panel/` en `api.py`: entrar, salir, `Depends` de sesión, cabeceras (CSP, X-Frame-Options, no-store), límite por IP, auditoría y 404 con el panel desactivado. Verificar con pruebas en `tests/asistente/test_panel_acceso.py`.

## 4. Datos de las estadísticas

- [ ] 4.1 🟡 `asistente/panel/consultas.py`: resolver día, semana, mes y rango a UTC con `zoneinfo`, el periodo anterior, la validación del rango y si hay detalle. Verificar con pruebas de semana de lunes a domingo, mes de 30 y 31 días, límite de 366 días y errores.
- [ ] 4.2 🔴 Endpoints JSON GET `/panel/datos/resumen`, `/vacantes`, `/vacantes/lista`, `/embudo` e `/ia`, con `periodo`, `anterior`, `series` y `detalle_disponible`. Verificar con pruebas sobre bases de prueba, comprobando que ninguna respuesta contiene campos personales y que el POST responde 405.

## 5. Página del panel

- [ ] 5.1 🔴 `assets/asistente/panel/` con `index.html`, `panel.css` (claro, oscuro y celular), `panel.js` (secciones, selector de periodo en la URL, flechas, calendario, comparación y bajada de detalle) y Chart.js fijo con su licencia. Verificar abriendo la página con datos de prueba en el navegador del panel de vista previa, a 375 px y en escritorio.
- [ ] 5.2 🟡 Vistas Resumen, Vacantes (gráficos, tabla filtrable con enlaces), Embudo (con el estado de las fuentes) e IA. Verificar con una prueba de navegador que el total de la tabla filtrada coincide con el del gráfico, y que el aviso de detalle borrado aparece con un día de hace 120 días.

## 6. Documentación y despliegue

- [ ] 6.1 🟢 Documentar el panel en `docs/asistente/` (cómo entrar, qué muestra, cómo agregar admins) y en `deploy/INSTALAR.md` (activar y vuelta atrás). Verificar que los enlaces de la documentación existen.
- [ ] 6.2 👤 En el Fedora: desplegar con `activo: false`, revisar el relleno en los logs, activar el panel con los admins, reiniciar `buscador-asistente.service` y entrar con `/panel` desde Telegram. Verificar con una captura del panel con datos reales.
