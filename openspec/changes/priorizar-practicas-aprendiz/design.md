# Design

## Context

La rotación (`buscador_vacantes/rotacion.py`) arma en cada corrida un lote de `Consulta(keyword, grupo)`. Toma `reservado_nucleo` consultas del núcleo y el resto del presupuesto de la cola larga, con una posición persistente por fuente y grupo. `Fuente.ejecutar` recorre el lote hasta `presupuesto` y cada consulta es un request a la primera página (`construir_peticion(keyword)`).

Datos verificados desde el servidor el 2026-10-04:
- **Computrabajo:** la página 1 está ordenada por relevancia, con fechas mezcladas entre "Ayer" y "Hace 3 días". `?p=2` devuelve ofertas distintas y `by=publicationtime` no cambia el orden. Hay 20 ofertas por página; "practicante sistemas" reporta 70 en 3 días y "aprendiz sistemas" 72.
- **elempleo:** `?page=2` devuelve 20 ofertas distintas a las de la página 1.
- **Magneto:** ya pide `order=publish_date DESC`, así que la página 1 trae lo más nuevo.
- Los rechazos de la IA a practicantes y aprendices fueron correctos. El cuello de botella está en lo que se busca, no en lo que se filtra.

## Goals / Non-Goals

**Goals:**
- Que la mayoría de los requests de cada corrida busquen prácticas, pasantías o aprendizaje.
- Ver todas las ofertas recientes de las consultas del núcleo, no solo las 20 más "relevantes".
- Cubrir la jerga colombiana (ADSO, etapa productiva, práctica profesional, últimos semestres) y los títulos en inglés con nivel.

**Non-Goals:**
- Fuentes nuevas, como el Servicio Público de Empleo. Van en otro change.
- Paginar la cola larga.
- Paginar LinkedIn: es la fuente más sensible a bloqueos y ya filtra por nivel.
- Cambiar los filtros por reglas, el prompt del clasificador o el formato de los mensajes.
- Palabras clave distintas por fuente.

## Decisions

**1. Núcleo exclusivo de prácticas, con 14 términos.**
- practicante sistemas
- practicante TI
- practicante ingeniería de sistemas
- practicante desarrollo de software
- aprendiz SENA
- aprendiz sistemas
- aprendiz ADSO
- aprendiz análisis y desarrollo de software
- aprendiz técnico en sistemas
- pasante tecnología
- pasantía ingeniería de sistemas
- práctica profesional ingeniería de sistemas
- estudiante últimos semestres ingeniería de sistemas
- trainee tecnología

"junior TI" y "desarrollador junior" pasan a la cola larga (grupo `general` y `desarrollo`). "practicante desarrollo" sale de la cola larga porque su variante ya está en el núcleo. Se descartó dejar los términos junior en el núcleo con más presupuesto: diluye la prioridad y es justo lo que hoy llena el canal de soporte e infraestructura.

**2. Paginación del núcleo con `paginas_nucleo`.**
- `Consulta` gana el campo `pagina: int = 1`.
- `calcular_lote(..., paginas_nucleo)` expande cada palabra clave del núcleo en `Consulta(k, NUCLEO, 1..P)` y asigna a la cola larga el presupuesto restante: `presupuesto - reservado_nucleo × P`.
- `construir_peticion(keyword, pagina=1)` recibe la página. Computrabajo agrega `p=N` desde la 2 y elempleo agrega `page=N`; las demás fuentes ignoran el parámetro.
- Cada fuente declara `tamano_pagina` (20 en Computrabajo y elempleo) y `soporta_paginas`. La corrida usa `paginas_nucleo` solo si la fuente lo soporta; si no, usa 1 y lo deja en el log.
- **Corte:** si una página devuelve menos vacantes que `tamano_pagina` (o falla), `ejecutar` omite las páginas siguientes de esa palabra clave. El presupuesto que sobra no se reasigna, para que el cálculo siga siendo simple y predecible.
- **Rotación:** `avanzar_lote` cuenta solo las consultas del núcleo con `pagina == 1`, así que avanza por palabra clave.
- **Validación:** `config.Fuente` rechaza `reservado_nucleo × paginas_nucleo > presupuesto`, que generaliza la regla actual.
- Se descartó paginar hasta agotar los resultados: el costo es impredecible y aumenta el riesgo de bloqueo. Se descartó también cambiar `pubdate` a 1 día: no arregla el orden por relevancia.

**3. Presupuestos.**

| Fuente | Presupuesto | Núcleo (kw × págs) | Cola larga | Ciclo del núcleo |
|---|---|---|---|---|
| LinkedIn | 3 (=) | 2 × 1 | 1 | 7 corridas ≈ 3,5 h |
| Computrabajo | 8 (antes 4) | 2 × 3 | 2 | 7 corridas ≈ 3,5 h |
| elempleo | 5 (antes 3) | 2 × 2 | 1 | 7 corridas ≈ 3,5 h |
| Magneto | 4 (antes 3) | 2 × 1 | 2 | 7 corridas ≈ 3,5 h |
| GetOnBoard | 5 (=) | 1 × 1 | 4 | sin cambio |

Con 3 páginas de Computrabajo y `pubdate=3`, cada consulta del núcleo cubre ~60 de las ~70 ofertas de los últimos 3 días, y se repite cada 3,5 h.

**4. Cola larga.**
- Salen: SysOps, CloudOps, AWS junior, Azure junior, técnico de redes, telecomunicaciones junior y practicante desarrollo.
- Entran por rol: practicante soporte, practicante redes, practicante QA y practicante ciberseguridad.
- Entran en inglés: "Software Engineer Intern", "Junior Software Engineer", "Junior Java Developer", "Spring Boot junior", "Junior QA Engineer" y "Junior Data Analyst". Solo se agregan títulos que nombran el nivel: sin él, en Computrabajo, elempleo y Magneto traen sobre todo vacantes senior.

**5. La regla "núcleo ≥ 50 % en fuentes sin filtro nativo" se verifica con una prueba de configuración, no en tiempo de ejecución.**
Es una política del `config.yaml` del proyecto, no una restricción del modelo de datos. Validarla en pydantic impediría configuraciones de prueba legítimas. Lo que sí se valida al cargar es que la reserva quepa en el presupuesto.

**6. Recuperar las vacantes sembradas por la cola `por_enviar`.**
Paso operativo que se hace una sola vez, con un script fuera del repositorio:
1. Respaldar la base.
2. Borrar de `vistas` las 26 vacantes sembradas: las 27 de TI menos "Programador de manteniminento Junior", que pasó el filtro por una errata.
3. Insertarlas en `por_enviar`.

La siguiente corrida las publica con el mecanismo de reintento existente, que descarta por huella las que ya se hubieran enviado.

## Risks / Trade-offs

- **[25 requests por corrida en lugar de 18 → más riesgo de bloqueo]** → Computrabajo hace 8 requests cada 30 min, con pausas de 4–10 s. El cooldown escalonado y los incidentes ya cubren un bloqueo; si aparece `computrabajo:bloqueo`, se baja `paginas_nucleo` a 2.
- **[Cola larga más lenta: elempleo y LinkedIn recorren 1 término por corrida]** → Con ~75 términos el ciclo completo tarda ~37 h en esas fuentes. Se acepta porque la prioridad es el núcleo, y Computrabajo y Magneto, con 2 por corrida, la cubren en ~19 h.
- **[Corte prematuro: una página con 20 artículos pero alguno mal formado devuelve 19 vacantes]** → Se pierde como máximo el resto de esa consulta en esa corrida; la siguiente pasada del núcleo, 3,5 h después, la cubre.
- **[Términos nuevos con pocos resultados ("aprendiz ADSO")]** → Tras 24 h se revisa el rendimiento por keyword en `intentos` y se poda lo que no rinda.
- **[Las vacantes recuperadas no traen ubicación, modalidad ni salario]** → El formato tolera campos vacíos. El enlace lleva a la oferta completa.

## Migration Plan

1. Desplegar: commit y push, luego `git pull` en `~/buscador-vacantes`, en el servidor. El timer toma el código y el `config.yaml` nuevos en la siguiente corrida; no hace falta reiniciar nada.
2. La posición de rotación guardada se aplica módulo el largo de la lista nueva, así que no hay que reiniciarla.
3. Rollback: `git revert` del commit y `git pull`.
