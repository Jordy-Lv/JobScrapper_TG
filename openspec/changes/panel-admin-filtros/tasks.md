## 1. Capa de configuración

- [ ] 1.1 🟡 `cargar_configuracion` con la capa `config.panel.yaml`, la lista blanca `CLAVES_PANEL`, la caída a dos capas si es inválida y respetando `BUSCADOR_SIN_CONFIG_LOCAL`. Agregar `config.panel.yaml` a `.gitignore` y `asistente.panel.dias_prueba` al modelo y a `config.yaml`. Verificar con pruebas en `tests/comun/test_config.py`: orden de capas, clave no permitida, capa inválida y pruebas aisladas.
- [ ] 1.2 🟡 Aviso al dueño desde el radar cuando se ignora la capa, como máximo uno cada 24 horas por contenido. Verificar con una prueba del aviso y su deduplicación.

## 2. Descartadas

- [ ] 2.1 🟡 Esquema 5 de `vacantes.db`: tabla `descartadas` y su limpieza por `dias_prueba`. Verificar con pruebas de migración y limpieza en `tests/comun/`.
- [ ] 2.2 🟡 Guardar las rechazadas en `radar/corrida.py` con su motivo, sin cambiar el embudo ni lo publicado. Verificar con una prueba de corrida con fixtures que compara las cifras antes y después.

## 3. Edición en el servidor

- [ ] 3.1 🔴 `asistente/panel/edicion.py`: leer el valor vigente y el origen de cada sección, comparar, validar con las tres capas, guardar de forma atómica con control de versión (409), restaurar, volver al repositorio y la tabla `config_versiones` (esquema de `asistente.db`). Verificar con pruebas de guardado, inválido, 409, restaurar, volver al repositorio y archivo editado a mano.
- [ ] 3.2 🔴 `probar(secciones)` con dos `Filtros` sobre `vistas`, `descartadas` y `detalles`, con el límite de 10 s. Verificar con pruebas de pérdidas, ganancias, cambio de categoría y ausencia de efectos (sin IA, sin escrituras).
- [ ] 3.3 🟡 Endpoints GET `/panel/datos/filtros`, `/fuentes` y `/filtros/versiones`, y POST `/filtros/probar`, `/filtros/guardar`, `/filtros/restaurar` y `/filtros/repo`, con CSRF, límites de fuentes y auditoría. Verificar con pruebas en `tests/asistente/test_panel_filtros.py`.

## 4. Página

- [ ] 4.1 🔴 Editor de chips, reordenar áreas (arrastrar y ↑↓), formulario de fuentes, resultados de la prueba, diferencias con confirmación, historial y `sessionStorage` en `assets/asistente/panel/`. Verificar en el navegador del panel de vista previa, en escritorio y a 375 px, con un guardado completo, un 409 simulado y una restauración.

## 5. Documentación y despliegue

- [ ] 5.1 🟢 Documentar en `docs/asistente/` la edición de filtros, la capa `config.panel.yaml` y cómo volver atrás, y en `deploy/INSTALAR.md` el permiso de escritura. Verificar que los enlaces existen.
- [ ] 5.2 👤 En el Fedora: confirmar que el radar y el asistente comparten usuario y carpeta, guardar un cambio de prueba en la lista negra, ver que la siguiente corrida lo aplica y restaurar. Verificar con el log de la corrida y el historial del panel.
