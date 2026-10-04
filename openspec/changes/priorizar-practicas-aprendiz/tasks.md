# Tasks

## 1. Paginación del núcleo

- [x] 1.1 Agregar `paginas_nucleo: int = Field(1, ge=1)` a `config.Fuente` y cambiar la validación a `reservado_nucleo × paginas_nucleo <= presupuesto`, con un mensaje claro. Verificar con una prueba en `tests/test_config.py` que 3 × 3 con presupuesto 8 se rechaza.
- [x] 1.2 Agregar `pagina: int = 1` a `rotacion.Consulta`. `calcular_lote` debe recibir `paginas_nucleo` y expandir el núcleo en páginas consecutivas por palabra clave, y `avanzar_lote` debe contar solo `pagina == 1` del núcleo. Verificar con pruebas en `tests/test_fechas_rotacion.py`: lote 2 kw × 3 págs + 2 de cola larga con presupuesto 8; avance del núcleo en 2; regresión del caso de 1 página.
- [x] 1.3 En `fuentes/base.py`:
  - Cambiar a `construir_peticion(keyword, pagina=1)` y que `consultar` pase `consulta.pagina`.
  - Agregar `soporta_paginas = False` y `tamano_pagina`.
  - En `ejecutar`, omitir las páginas siguientes de una palabra clave si la anterior trajo menos de `tamano_pagina` vacantes o falló.
  - Registrar la página en el log del intento.

  Actualizar la firma en todas las fuentes y en las fuentes falsas de las pruebas. Verificar con pruebas en `tests/test_fuente_base.py` el corte por página incompleta, el corte por error y que una página completa continúa.
- [x] 1.4 Computrabajo (`soporta_paginas = True`, `tamano_pagina = 20`, `p=N` desde la página 2) y elempleo (`page=N` desde la página 2). Verificar con pruebas de `construir_peticion` que la página 1 conserva la URL actual y la 2 agrega el parámetro.
- [x] 1.5 En `corrida._consultar`, pasar `paginas_nucleo` a `calcular_lote` solo si la clase de la fuente `soporta_paginas`; si no, usar 1 y dejar una advertencia en el log. Verificar que `uv run pytest` pasa completo y que `uv run ruff check` y `uv run ruff format --check` no reportan nada.

## 2. Palabras clave y presupuestos

- [x] 2.1 Reescribir `palabras_clave.nucleo` en `config.yaml` con los 14 términos de prácticas del design. Mover "junior TI" (a `general`) y "desarrollador junior" (a `desarrollo`), y quitar "practicante desarrollo" de la cola larga. Agregar "adso" a los términos del área `desarrollo` de los filtros, para que "Aprendiz ADSO" se acepte por reglas en lugar de quedar dudosa.
- [x] 2.2 Podar y ampliar la cola larga:
  - Quitar SysOps, CloudOps, AWS junior, Azure junior, técnico de redes y telecomunicaciones junior.
  - Agregar practicante soporte, practicante redes, practicante QA y practicante ciberseguridad.
  - Agregar los 6 títulos en inglés con nivel: "Software Engineer Intern", "Junior Software Engineer", "Junior Java Developer", "Spring Boot junior", "Junior QA Engineer" y "Junior Data Analyst".
- [x] 2.3 Ajustar `fuentes` (presupuesto/reservado_nucleo/paginas_nucleo): LinkedIn 3/2/1, Computrabajo 8/2/3, elempleo 5/2/2 y Magneto 4/2/1, con GetOnBoard sin cambio. Verificar con `uv run buscador.py --dry-run --fuente computrabajo` que hace 6 requests del núcleo (páginas 1–3 de 2 keywords) y 2 de la cola larga.
- [x] 2.4 Pruebas en `tests/test_config.py`:
  - El núcleo no contiene "junior".
  - No hay términos repetidos entre el núcleo y la cola larga.
  - En las fuentes activas sin `filtra_nivel` se cumple `reservado_nucleo × paginas_nucleo × 2 >= presupuesto`.
  - Actualizar las aserciones de presupuesto existentes.

  Verificar que `uv run pytest` pasa.
- [x] 2.5 Actualizar `README.md`: el grupo núcleo es exclusivo de prácticas y se describe `paginas_nucleo`. Verificar que coincide con `config.yaml`.

## 3. Despliegue y recuperación

- [ ] 3.1 Commit y push a `origin/main` (sin atribución a IA), luego `git pull` en el servidor. Verificar en el log de la siguiente corrida que `requests` muestra 8 en Computrabajo, 5 en elempleo y 4 en Magneto, o menos si hubo cortes por página incompleta.
- [ ] 3.2 En el servidor, ejecutar el script de recuperación de las 26 vacantes sembradas (respaldo de la base, borrar las vistas y encolar en `por_enviar`). Verificar que la siguiente corrida las publica y que `por_enviar` queda en 0.

## 4. Verificación en producción

- [ ] 4.1 Tras 24 h, consultar `intentos` y `vistas`: proporción de requests del núcleo por fuente, resultados por keyword nueva, cortes de paginación y cuántas vacantes de categoría `practicas` se enviaron frente al 2026-10-04. Entregar el resultado al usuario y podar las keywords que devuelvan 0 resultados.
