## Why

Hoy, para cambiar un filtro hay que:
- editar `config.yaml`, que tiene casi 1400 líneas;
- hacer commit y `git pull` en el Fedora;
- esperar la siguiente corrida.

No se puede saber de antemano qué vacantes cambiarían. La propia configuración lo reconoce en la lista negra: «se edita aquí hasta que exista el panel». El dueño quiere ajustar los filtros desde la web, de forma completa y fácil, sin riesgo de romper el radar.

## What Changes

- **Vista Filtros** del panel, con un editor por sección:
  - **palabras clave**: núcleo y cola larga por área;
  - **exclusiones**: seniority, años de experiencia, días máximos de publicación, frases ignoradas y lista negra de empresas y palabras;
  - **niveles**: términos de práctica, evidencia de práctica en el título y la descripción, y términos de junior;
  - **áreas de TI**: orden de prioridad (se reordena arrastrando) y términos de cada área; también los términos de TI genéricos, los disparadores de dudosa, las áreas que no son TI y el call center;
  - **ubicación**: ciudad base, términos de modalidad (remoto, híbrido, presencial), Colombia, LATAM, exterior y patrones de restricción.

  Cada lista se edita con chips: agregar, quitar y buscar, con aviso de duplicados y de términos que no coinciden con nada por la normalización.
- **Vista Fuentes**, editable: activar o desactivar cada portal y ajustar `presupuesto`, `reservado_nucleo` y `paginas_nucleo` dentro de límites seguros.
- **Probar antes de guardar**: aplica los filtros nuevos y los actuales a las vacantes de los últimos `panel.dias_prueba` días (7 por defecto), aceptadas y rechazadas, y muestra:
  - cuáles pasan de aceptada a rechazada, y por qué regla;
  - cuáles pasan de rechazada a aceptada;
  - cuáles cambian de categoría.

  No llama a la IA ni publica nada.
- **Guardar con seguridad**:
  - vista de diferencias antes de confirmar y comentario opcional;
  - validación con los mismos modelos de `comun/config.py`;
  - escritura atómica en un archivo aparte, `config.panel.yaml` (fuera de git);
  - control de versión, para que dos admins no se pisen;
  - auditoría.

  El cambio rige desde la siguiente corrida del radar, y el panel muestra a qué hora es.
- **Historial y deshacer**: cada guardado es una versión con su autor, fecha, comentario y diferencias. Cualquier versión se puede restaurar, y cada sección puede **volver al valor del repositorio**.
- **El radar guarda las vacantes descartadas** (título, empresa, ubicación, modalidad, fuente y motivo) durante `panel.dias_prueba` días, para que la prueba pueda mostrar las que se ganarían. Hoy solo se guardan las aceptadas.
- **Capa de configuración nueva**: `cargar_configuracion` lee `config.yaml`, luego `config.local.yaml` y por último `config.panel.yaml`. El panel solo escribe las secciones permitidas. Si `config.panel.yaml` deja la configuración inválida, se ignora, la corrida sigue con la configuración anterior y se avisa al dueño.

## Capabilities

### New Capabilities

- `panel-admin-filtros`: edición de palabras clave, filtros y fuentes desde el panel, con prueba previa, diferencias, validación, versiones, deshacer y auditoría.
- `configuracion-panel`: la capa `config.panel.yaml` (qué secciones puede tocar, en qué orden se combina, qué pasa si es inválida) y la conservación de las vacantes descartadas para la prueba.

### Modified Capabilities

(ninguna: la evaluación de los filtros no cambia; solo cambia de dónde salen sus valores)

## Impact

- Depende de `panel-admin-metricas` (sesión, CSRF, auditoría y estructura de la página).
- Código:
  - `comun/config.py` (capa `config.panel.yaml`, lista de secciones editables, `panel.dias_prueba`);
  - nuevo `asistente/panel/edicion.py` (validar, comparar, probar, guardar y restaurar);
  - `radar/corrida.py` y `comun/estado.py` (tabla `descartadas`, esquema 5, con limpieza);
  - `asistente/datos.py` (tabla `config_versiones`);
  - `radar/filtros.py` sin cambios de lógica: se reutiliza `Filtros.evaluar` para la prueba.
- Recursos: sección Filtros y Fuentes en `assets/asistente/panel/` (editor de chips, reordenar arrastrando, diferencias, historial).
- Configuración: `config.panel.yaml` en `.gitignore`, y `panel.dias_prueba` en `config.yaml`.
- Pruebas: `tests/comun/test_config.py` (capas y archivo inválido), `tests/asistente/test_panel_filtros.py` y `tests/radar/` (descartadas).
- Despliegue: el servicio del asistente necesita permiso de escritura en la carpeta del proyecto, que ya tiene por ser el mismo usuario. Se documenta en `deploy/INSTALAR.md`.
