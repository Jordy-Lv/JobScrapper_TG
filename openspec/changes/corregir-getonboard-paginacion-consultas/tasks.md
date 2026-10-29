## 1. Configuración por fuente

- [x] 1.1 🟡 Crear una rama propia desde `main` para este change y verificar con `git status` que no arrastra los cambios sin confirmar de la rama actual
- [x] 1.2 🟡 Añadir a `buscador_vacantes/comun/config.py` el modelo `PalabrasPropias` (`nucleo` con mínimo 1, `cola_larga` plana opcional, sin cadenas vacías) y el campo opcional `Fuente.palabras_clave`, con validación que rechace combinarlo con `opciones.consulta.modo = "or"`; verificar con pruebas nuevas en `tests/comun/test_config.py` (núcleo vacío rechazado, palabra vacía rechazada, combinación con `or` rechazada, fuente sin el campo carga igual)
- [x] 1.3 🟡 Cambiar `corrida._consultar` para elegir núcleo y cola por fuente (propias si existen, globales si no); verificar con una prueba de corrida que GetOnBoard recibe sus listas y Computrabajo las globales

## 2. Fuente GetOnBoard

- [x] 2.1 🟡 En `buscador_vacantes/radar/fuentes/getonboard.py`: declarar `soporta_paginas = True`, usar `pagina` en `"page"`, guardar en `parsear` si `meta.page < meta.total_pages` y sobrescribir `pagina_completa` con ese valor (sin `meta` o inválido → `False`); verificar con pruebas `respx` en `tests/radar/test_getonboard.py`: se pide `page=2` cuando `total_pages=3`, no se pide con `total_pages=1`, se pide aunque el filtro de nivel deje pocas ofertas, no se pide sin `meta`
- [x] 2.2 🟢 Verificar que las pruebas existentes de `test_getonboard.py` (parser con fixture, campos faltantes, JSON inválido) siguen en verde sin tocarlas

## 3. Configuración y documentación

- [x] 3.1 🟢 En `config.yaml`, sección `fuentes.getonboard`: pasar a `presupuesto: 6`, `reservado_nucleo: 2`, `paginas_nucleo: 2` y añadir `palabras_clave` con el núcleo (`practicante`, `aprendiz`, `pasante`, `pasantía`, `trainee`, `internship`) y la cola larga (`junior`, `soporte`, `sistemas`, `QA`, `datos`, `redes`, `devops`, `ciberseguridad`, `analista`, `desarrollador`); actualizar el comentario de la sección; verificar con la prueba de configuración que ninguna palabra propia de GetOnBoard contiene espacios y que 2 × 2 ≤ 6
- [x] 3.2 🟢 Actualizar `tests/comun/test_config.py` donde fija el presupuesto de GetOnBoard (línea 66) y añadir la comprobación del núcleo propio sin frases ni «junior»; verificar con `uv run pytest tests/comun/test_config.py`
- [x] 3.3 🟢 Actualizar la fila de GetOnBoard en `docs/radar/plan-mejora-scraping/estado-actual.md` (presupuesto 6, página según `total_pages`, palabras propias) y, si `README.md` o `deploy/INSTALAR.md` mencionan el presupuesto, ajustarlos; verificar con `grep -n getonboard` sobre esos archivos

## 4. Verificación

- [x] 4.1 🟡 Correr `uv run pytest tests/radar tests/comun` y `uv run ruff check` / `ruff format --check` sobre lo tocado; verificar que todo queda en verde
- [x] 4.2 🟡 Con las listas nuevas, repetir contra la API real una consulta por palabra (script de lectura, sin escribir estado: `--dry-run` no corre en Windows) y anotar en este `tasks.md` cuántas ofertas devuelve cada palabra y cuántas pasan el filtro de nivel; verificar que ninguna palabra del núcleo devuelve 0 por ser una frase
  - Medición contra la API real (2026-10-29):
    | Grupo | Palabra | HTTP | Crudas (pág 1) | Total páginas | Pasan filtro de nivel |
    |---|---|---|---|---|---|
    | núcleo | `practicante` | 200 | 5 | 1 | 5 |
    | núcleo | `aprendiz` | 200 | 10 | 1 | 2 |
    | núcleo | `pasante` | 200 | 1 | 1 | 0 |
    | núcleo | `pasantía` | 200 | 1 | 1 | 0 |
    | núcleo | `trainee` | 200 | 50 | 2 | 3 |
    | núcleo | `internship` | 200 | 9 | 1 | 9 |
    | cola larga | `junior` | 200 | 50 | 3 | 36 |
    | cola larga | `soporte` | 200 | 50 | 5 | 7 |
    | cola larga | `sistemas` | 200 | 50 | 8 | 8 |
    | cola larga | `QA` | 200 | 50 | 7 | 6 |
    | cola larga | `datos` | 200 | 50 | 12 | 5 |
    | cola larga | `redes` | 200 | 50 | 3 | 5 |
    | cola larga | `devops` | 200 | 50 | 5 | 3 |
    | cola larga | `ciberseguridad` | 200 | 31 | 1 | 4 |
    | cola larga | `analista` | 200 | 50 | 2 | 10 |
    | cola larga | `desarrollador` | 200 | 50 | 4 | 1 |
    Ninguna palabra del núcleo devolvió 0 ofertas crudas; todas respondieron con resultados reales.
- [ ] 4.3 👤 Desplegar al Fedora y, tras un par de días, revisar en la tabla `intentos` el `items` de GetOnBoard por consulta; verificar que dejó de haber consultas con 0 por frases largas
