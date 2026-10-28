## 1. Precondiciones

- [x] 1.1 Confirmar que `unificar-asistente-en-main` está integrada y desplegada, y que la suite está en verde en `main`
- [x] 1.2 Confirmar con el dueño el reparto de módulos de `design.md` (sobre todo `ia_cliente` y `notificador_telegram`) y que ninguna otra sesión use la carpeta (decidido por el dueño: `ia_cliente` y `notificador_telegram` van en `radar/`)
- [x] 1.3 Crear la rama `ordenar-estructura-paquetes` desde `main` y anotar el resultado base de la suite (base: 1111 pasan, 3 fallan por Windows, 2 omitidas)

## 2. Mover código con git mv

- [x] 2.1 Crear `comun/` y mover `config`, `estado`, `modelo`, `normalizar`, `fechas`, `registro`, `lock` (commit solo de movimiento)
- [x] 2.2 Crear `radar/` y mover los módulos del radar y `fuentes/` (commit solo de movimiento)
- [x] 2.3 Añadir los `__init__.py` necesarios
- [x] 2.4 Actualizar imports en `buscador_vacantes/`, `buscador.py` y `asistente/` (commit aparte)
- [x] 2.5 Revisar rutas por texto: cadenas de parcheo, `sys.modules[...]`, `RAIZ` y rutas relativas a `config.yaml`, `data/` y `deploy/`

## 3. Mover pruebas

- [x] 3.1 `git mv` de las pruebas a `tests/comun/`, `tests/radar/` y `tests/asistente/`, con `conftest.py` y fixtures accesibles
- [x] 3.2 Actualizar imports y cadenas de parcheo (`tests/test_simulacion.py`, `tests/test_asistente_servicio.py`)
- [x] 3.3 Añadir la prueba de arquitectura de dependencias entre paquetes (regla: comun <- asistente <- radar; el radar puede importar del asistente, decisión del dueño)

## 4. Verificación

- [x] 4.1 Suite completa en verde sin tocar aserciones de comportamiento y `ruff` limpio (tras el movimiento: 1111 pasan, 3 fallan por Windows como en la base, 2 omitidas; más 4 de arquitectura; ruff sin avisos nuevos)
- [x] 4.2 Probar `uv run buscador.py` en modo prueba, `resumen` y `asistente servicio` (sin red real) (en local con `--dry-run`: incidente simulado, `asistente servicio` y `empaquetar-extension` ok; el nombre del módulo en los registros ahora lleva la carpeta)
- [x] 4.3 Comprobar `git log --follow` en tres módulos movidos

## 5. Planes de los changes abiertos

- [x] 5.1 Construir la tabla de rutas antiguo→nuevo
- [x] 5.2 Actualizar rutas en `proposal/design/tasks` de `linkedin-detalle-vacantes`, `preguntas-encuesta-con-botones-y-redaccion-ia`, `reenviar-tarjeta-preguntas-al-retomar-alta`, `linkedin-peticiones-eficientes` y `filtro-vacantes-limpias`, sin tocar tareas ya marcadas
- [x] 5.3 Actualizar README, `deploy/INSTALAR.md` y `openspec/config.yaml` si citan rutas movidas

## 6. Cierre (👤)

- [x] 6.1 Pedir confirmación al dueño para integrar en `main` y desplegar (confirmado por el dueño; `main` en `f6cd43f`, subido a `origin`)
- [x] 6.2 `git pull` en el Fedora, comprobar los tres servicios y actualizar la memoria (fase 1 hecha) (desplegado por el dueño a las 03:08; corrida 499 a las 03:32 y 15 más sin errores de importación; asistente activo sin reinicios)
