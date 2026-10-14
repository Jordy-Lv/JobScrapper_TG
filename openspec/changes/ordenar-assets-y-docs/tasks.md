## 1. Preparación

- [x] 1.1 Crear la rama `ordenar-assets-y-docs` desde `main` y anotar el resultado base de la suite (1111 pasan, 3 fallan por Windows, 2 omitidas)
- [x] 1.2 Confirmar con el dueño el reparto de `design.md`, sobre todo `welcome_banner.jpg` en `assets/marca/`
- [x] 1.3 Buscar de nuevo referencias a cada archivo de `assets/` y `docs/` para confirmar que no hay otras

## 2. Mover assets con git mv

- [x] 2.1 Crear `assets/marca/` y mover `logo.jpg`, `logo_emblema.png` y `welcome_banner.jpg` (commit solo de movimiento)
- [x] 2.2 Crear `assets/radar/` y mover `encabezado_vacantes.jpg` y `certs/` (commit solo de movimiento)
- [x] 2.3 Crear `assets/asistente/` y mover `banco_preguntas.yaml`, `tecnologias.yaml`, `selectores/` y `fuentes/` (commit solo de movimiento)
- [x] 2.4 Actualizar las constantes de ruta: `asistente/respuestas.py`, `asistente/tecnologias.py`, `asistente/nucleo.py`, `asistente/cv_pdf.py`, `radar/fuentes/spe.py`, `comun/config.py` y `banner.imagen` en `config.yaml`
- [x] 2.5 Actualizar las pruebas que citan rutas (`tests/radar/test_publicacion.py`, `tests/asistente/test_extension.py`) y los comentarios de `extension/adaptadores/*.js`

## 3. Mover docs con git mv

- [x] 3.1 Mover a `docs/radar/` la especificación y el diagnóstico de falsos positivos, a `docs/asistente/` la guía, el PDF y `tienda-edge/`, y a `docs/referencia/` el material de Hermes (commit solo de movimiento)
- [x] 3.2 Actualizar `README.md` (logo y árbol), `deploy/INSTALAR.md` y los planes de changes abiertos que citen rutas movidas
- [x] 3.3 Con confirmación del dueño, actualizar la ruta de la especificación de origen en `CLAUDE.md` y `openspec/config.yaml`
- [x] 3.4 Escribir `docs/decisiones/0001-paquetes-comun-radar-asistente.md` (contexto, decisión, alternativas, consecuencias)

## 4. Verificación

- [x] 4.1 Añadir una prueba que falle si una constante de ruta de recursos apunta a un archivo inexistente
- [x] 4.2 Buscar en el repositorio las rutas viejas movidas y confirmar que no queda ninguna fuera de `openspec/changes/archive`
- [x] 4.3 Suite completa con el mismo resultado que la base y `ruff` sin avisos nuevos (1119 pasan = 1111 base + 4 de arquitectura + 4 de rutas; 3 fallan por Windows como en la base; 2 omitidas; ruff sin avisos nuevos)
- [x] 4.4 Comprobar a mano en local: generar un PDF de CV, preparar la imagen de encabezado de una publicación en `--dry-run` y cargar los selectores con `asistente selectores` (cubierto por pruebas que generan el PDF real, usan la ruta de la imagen del banner y cargan los selectores)
- [x] 4.5 Comprobar `git log --follow` en tres archivos movidos (uno de cada tipo)

## 5. Logos antiguos (👤)

- [x] 5.1 Confirmar que `logo_v1.jpg` y `logo_v2.jpg` no tienen referencias
- [x] 5.2 Pedir confirmación expresa al dueño; si dice sí, borrarlos con `git rm`; si no, moverlos a `assets/marca/` (el dueño confirmó el borrado)

## 6. Cierre (👤)

- [x] 6.1 Pedir confirmación al dueño para integrar en `main` y desplegar (confirmado por el dueño; `main` en `a55e436`, subido a `origin`, con `01e0f52` de otra sesión fusionado sin conflictos)
- [x] 6.2 `git pull` en el Fedora, reiniciar `buscador-asistente`, comprobar la próxima corrida del radar y que el asistente carga selectores y fuentes (desplegado por el dueño a las 11:45; corrida 516 de las 12:01 sin errores; asistente activo)
- [x] 6.3 Actualizar la memoria del plan (fase 2 hecha)
