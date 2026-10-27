## Why

El código del buscador (radar) y el del asistente conviven mezclados: `buscador_vacantes/` tiene 25 módulos planos del radar junto al subpaquete `asistente/`, y `tests/` mezcla pruebas de ambos en una sola carpeta plana. Eso dificulta saber qué pieza depende de cuál y deja a `asistente/` importando módulos «comunes» (`config`, `estado`, `normalizar`, `fechas`) sin que se vea. Ordenar las carpetas es la fase 1 del plan de reestructura y no debe cambiar el comportamiento.

## What Changes

- Crear los paquetes `buscador_vacantes/comun/` (infraestructura compartida) y `buscador_vacantes/radar/` (con `fuentes/`), y mantener `buscador_vacantes/asistente/` donde ya está.
- Mover con `git mv` (conserva historial) los módulos planos a su paquete (reparto en `design.md`) y actualizar todos los imports.
- Mover las pruebas a `tests/comun/`, `tests/radar/` y `tests/asistente/`, quitando el prefijo `asistente_` de los nombres donde sobre.
- Actualizar las rutas en los planes (`proposal/design/tasks`) de los changes abiertos que mencionan archivos movidos.
- `buscador.py` queda **igual** en comportamiento, y con él los servicios systemd (`ExecStart ... buscador.py`); solo puede cambiar la línea que importa `main`.
- **Sin** cambios de lógica, de `config.yaml`, de esquemas SQLite ni de mensajes.
- **Precondición:** la fase 0 (`unificar-asistente-en-main`) integrada en `main` y desplegada; mover antes provoca conflictos en cada archivo movido.

## Capabilities

### New Capabilities
- `estructura-paquetes`: organización del código en `comun/`, `radar/` y `asistente/`, con regla de dependencias entre ellos (`comun` ← `asistente` ← `radar`) y equivalencia de comportamiento.

### Modified Capabilities

## Impact

- Código: ~25 módulos y ~60 archivos de prueba cambian de ruta; todos los imports internos y las cadenas de parcheo en pruebas (`"buscador_vacantes.simulacion.…"`, `sys.modules[...]`).
- Despliegue: ninguna unidad systemd cambia; tras el `git pull` el Fedora corre el mismo comando.
- Changes abiertos: `linkedin-detalle-vacantes`, `preguntas-encuesta-con-botones-y-redaccion-ia` y `reenviar-tarjeta-preguntas-al-retomar-alta` (con trabajo sin confirmar en el árbol de trabajo) y los demás que citan rutas; se actualizan solo los textos de los planes, no su código.
- Riesgo de coordinación: trabajo sin confirmar en otras ramas queda con rutas viejas hasta rebasarlo.
