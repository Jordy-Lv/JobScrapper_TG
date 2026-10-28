## Context

Ver `proposal.md` para el motivo. Lo que hay hoy, verificado en el código y contra la API (2026-10-28):

- `corrida._consultar` (`radar/corrida.py:276`) toma `nucleo` y `cola` de `config.palabras_clave` **una vez** y se las da a todas las fuentes. No existe una lista por fuente; `Fuente.opciones` (`comun/config.py:158`) es un diccionario libre, pero solo LinkedIn usa `opciones.consulta` para combinar palabras con `OR`.
- `rotacion.calcular_lote` reparte el presupuesto entre `reservado_nucleo` palabras del núcleo (cada una con `paginas_nucleo` páginas) y la cola larga (solo página 1). `Fuente.ejecutar` omite las páginas siguientes de una palabra si `pagina_completa(vacantes)` da `False`.
- `GetOnBoard.construir_peticion` ignora `pagina` (`"page": 1`) y la clase no declara `soporta_paginas`, así que `corrida.py:332` fuerza `paginas = 1` con un aviso. Además, el `pagina_completa` por defecto cuenta `len(vacantes) >= tamano_pagina (20)` sobre las ofertas **ya filtradas por nivel**, que casi nunca llegan a 20 de 50.
- La API de búsqueda (`/api/v0/search/jobs`) devuelve `meta: {page, per_page, total_pages}`. Probado: es una búsqueda AND, y «practicante OR aprendiz», «practicante | aprendiz» y «practicante,aprendiz» devuelven 0. «practicante» da 5 ofertas, «aprendiz» 11, «internship» 9, «trainee» 50 (2 páginas), «junior» 50 (3 páginas). «intern», «SENA» y «práctica» devuelven 50 por coincidir como subcadena en descripciones («internacional», «buenas prácticas»): son ruido y quedan fuera.
- `SPE` ya resolvió el mismo problema de «página llena» contando las filas recibidas en vez de las filtradas (`radar/fuentes/spe.py:118-122`); sirve de patrón.

## Goals / Non-Goals

**Goals:**
- Que las consultas de GetOnBoard devuelvan resultados (una palabra) y que la paginación funcione de verdad.
- Palabras clave por fuente, opcionales y retrocompatibles, para no obligar a las demás fuentes a cambiar.
- Mantener cada pieza pequeña y probada con `respx` y un fixture.

**Non-Goals:**
- Cambiar el filtro de nivel, el descarte de remotos en inglés o el filtro de ubicación.
- Tocar las palabras clave globales ni las de Computrabajo, elempleo, Magneto, LinkedIn o SPE.
- Buscar por categoría o país en GetOnBoard (la API no ofrece `/countries/CO/jobs`: respondió 404) ni subir el volumen de forma artificial.
- Arreglar `--dry-run` en Windows (`signal.SIGALRM`); es otro change.

## Decisions

**1. Un campo opcional `palabras_clave` en cada fuente, no una opción libre.**
`Fuente` gana `palabras_clave: PalabrasPropias | None` con `nucleo` (mínimo 1) y `cola_larga` (lista plana, puede estar vacía). `corrida._consultar` elige por fuente: las propias si existen, las globales si no. Alternativas descartadas: (a) meterlo en `opciones` como diccionario libre, que no se valida al cargar y deja pasar un núcleo vacío o una frase; (b) editar la lista global, que rompería a las otras fuentes, que sí entienden frases («practicante sistemas» funciona en Computrabajo); (c) partir las frases en palabras dentro de `GetOnBoard.construir_peticion`, que escondería la regla en código y haría que 14 frases colapsen en las mismas 3 palabras.

**2. La cola larga propia es una lista plana, no por áreas.**
Las áreas de la lista global existen para armar consultas `OR` agrupadas, que GetOnBoard no admite. Para la rotación por palabra (`cola_larga_plana`) basta una lista.

**3. Las palabras propias no se combinan con `opciones.consulta.modo = "or"`.**
El modo `or` arma grupos con `palabras.grupos_nucleo()`, que solo conoce las globales. El validador de `Fuente` rechaza declarar ambas cosas, para que nadie espere un comportamiento que no existe.

**4. Paginación según `meta.total_pages`, con el patrón del SPE.**
`GetOnBoard` declara `soporta_paginas = True`, guarda en `parsear` si hay más páginas (`meta.page < meta.total_pages`) y sobrescribe `pagina_completa` para devolver ese valor. Sin `meta` o con un valor inválido, `False` (la página leída se trata como la última). `construir_peticion` pasa `pagina` a `page`. Alternativa descartada: dejar la heurística de `tamano_pagina`, que mide ofertas filtradas y cortaría en la página 1 casi siempre. El estado vive en la instancia, igual que `_filas_ultima_pagina` en el SPE: la fuente se crea por corrida y las consultas son secuenciales.

**5. Presupuesto 6 / 2 palabras / 2 páginas.**
Con 6 palabras de núcleo, 2 por corrida, el núcleo completa un ciclo cada 3 corridas (~1,5 h a la cadencia de :00 y :30). Las dos páginas solo se gastan en palabras con más de una (hoy «trainee»); las demás cuestan 1 request y liberan el resto. La cola larga (10 palabras, 2 por corrida, solo página 1) rota cada 5 corridas. El validador `reservado_nucleo × paginas_nucleo ≤ presupuesto` se cumple (4 ≤ 6). No se aplica la regla «núcleo ≥ mitad del presupuesto» porque GetOnBoard tiene `filtra_nivel: true`, igual que antes.

**6. «junior» va en la cola larga, no en el núcleo.**
La regla del proyecto exige que el núcleo sea solo de prácticas, pasantía y aprendizaje. «junior» (3 páginas, el término con más ofertas útiles) queda en la cola larga con una sola página por corrida. Si se quiere leerlo completo, es un ajuste de configuración posterior.

**Palabras elegidas** (todas probadas contra la API): núcleo `practicante`, `aprendiz`, `pasante`, `pasantía`, `trainee`, `internship`; cola larga `junior`, `soporte`, `sistemas`, `QA`, `datos`, `redes`, `devops`, `ciberseguridad`, `analista`, `desarrollador`. «pasante» y «pasantía» devuelven 1 oferta cada una y se mantienen por si el catálogo cambia.

## Risks / Trade-offs

- [El volumen sigue siendo bajo: el catálogo tiene ~4 ofertas junior de Colombia] → Es un techo del portal, no del recolector. La verificación mide ofertas recuperadas antes y después, no promete más.
- [Palabras sueltas como «sistemas» o «analista» devuelven ofertas de todos los niveles] → El filtro de `seniorities` las descarta; el costo es una petición. Aceptado porque son solo 2 de 6 requests y rotan.
- [Subcadenas ruidosas («intern», «SENA»)] → Se excluyen de las listas; la prueba de configuración impide frases, no subcadenas, así que la lista se revisa a mano.
- [La rama actual (`magneto-confirmacion-real-y-spe`) tiene cambios sin confirmar de otro trabajo] → Aplicar este change en una rama propia desde `main`, para no mezclar archivos (`extension/`, `asistente/`, `openspec/changes/magneto-encuesta-chat/`).
- [Las specs generales de rotación aún están en changes sin archivar] → Este change usa una capacidad propia (`busqueda-getonboard`) para no chocar con ellos al archivar.

## Migration Plan

1. Aplicar en una rama nueva desde `main`; no hace falta migrar la base: la rotación guarda posiciones por `fuente` y `grupo`, y al cambiar las listas se reinterpretan módulo el nuevo tamaño (`rotacion.avanzar`).
2. Probar con `uv run pytest tests/radar/test_getonboard.py tests/comun/test_config.py`.
3. Desplegar al Fedora con el flujo habitual del piloto; `config.yaml` es parte del despliegue. Para volver atrás basta revertir el bloque `getonboard` de `config.yaml` (quitar `palabras_clave` y restaurar 5/1/1); el código nuevo es inofensivo sin esa configuración.
4. Después de un par de días en el servidor, comparar la tabla `intentos` de GetOnBoard (`items` por consulta) con la de antes, desde el Fedora (👤 es del dueño: requiere el servidor).
