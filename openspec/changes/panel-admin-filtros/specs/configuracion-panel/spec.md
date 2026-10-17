## Purpose

Define cómo se combinan los valores que guarda el panel con `config.yaml` y `config.local.yaml` sin tocar los archivos del repositorio, y qué datos guarda el radar para que el panel pueda probar los filtros.

## ADDED Requirements

### Requirement: Capa config.panel.yaml
La carga de la configuración SHALL combinar, en este orden, `config.yaml`, `config.local.yaml` (si existe) y `config.panel.yaml` (si existe). Cada capa reemplaza los valores que trae, igual que hoy hace `config.local.yaml`. `config.panel.yaml` MUST contener solo estas claves:
- `palabras_clave`;
- `filtros`;
- `fuentes.<nombre>.activa`, `presupuesto`, `reservado_nucleo` y `paginas_nucleo`.

Si contiene cualquier otra clave, la capa entera se ignora. `config.panel.yaml` MUST estar fuera de git. Con `BUSCADOR_SIN_CONFIG_LOCAL=1` también se ignora.

#### Scenario: El panel manda sobre el repositorio
- **WHEN** `config.yaml` tiene `fuentes.magneto.activa: true` y `config.panel.yaml` tiene `false`
- **THEN** la configuración cargada tiene Magneto desactivada

#### Scenario: Clave no permitida
- **WHEN** `config.panel.yaml` trae `telegram.modo`
- **THEN** la capa se ignora entera, se registra el motivo en el log y la carga sigue con las otras dos capas

#### Scenario: Pruebas aisladas
- **WHEN** las pruebas corren con `BUSCADOR_SIN_CONFIG_LOCAL=1`
- **THEN** no se lee `config.panel.yaml`

### Requirement: Capa inválida no detiene el radar
Si la configuración que resulta con `config.panel.yaml` no pasa la validación, el sistema SHALL ignorar esa capa, cargar la configuración sin ella y seguir. Además MUST avisar al dueño por Telegram como máximo una vez cada 24 horas por el mismo contenido. Si la configuración es inválida sin esa capa, la carga falla como hoy.

#### Scenario: Archivo editado a mano con un error
- **WHEN** alguien edita `config.panel.yaml` en el servidor y deja `presupuesto: -1`
- **THEN** la corrida usa la configuración del repositorio y el dueño recibe un aviso con el error

### Requirement: Vacantes descartadas para la prueba
El radar SHALL guardar, en cada corrida, las vacantes que las reglas rechazan, con estos datos:
- clave, fuente, título, empresa, URL, ubicación y modalidad;
- motivo del rechazo y fecha.

Se conservan `asistente.panel.dias_prueba` días (7 por defecto) y la limpieza las borra después. Una vacante descartada varias veces MUST quedar una sola vez, con la fecha más reciente. Guardarlas MUST NOT cambiar qué se publica ni las cifras del embudo.

#### Scenario: Descarte guardado
- **WHEN** una corrida rechaza «Desarrollador Senior Java» por `seniority`
- **THEN** la vacante queda en las descartadas con el motivo `seniority`

#### Scenario: Limpieza de descartadas
- **WHEN** una descartada tiene más de 7 días
- **THEN** la limpieza la borra
