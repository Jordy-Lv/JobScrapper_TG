## 1. Comprobación real contra LinkedIn (🔴 manual, tras el cooldown)

- [ ] 1.1 Confirmar en el servidor (`ssh fedora`, tabla `fuentes_estado`) que el cooldown de LinkedIn terminó (hasta las 23:45 UTC del 2026-10-13) y que no hay corrida en curso. Verificar con `SELECT cooldown_hasta FROM fuentes_estado WHERE fuente='linkedin'`.
- [ ] 1.2 Con **una sola petición** de la variante Colombia (por ejemplo `uv run buscador.py --dry-run --fuente linkedin` con una configuración temporal de `presupuesto: 1`), comprobar que LinkedIn:
  - acepta `sortBy=DD` y devuelve primero lo más reciente (las fechas «Hace X» van de menor a mayor);
  - acepta una consulta con `OR` y comillas, con las 14 palabras del núcleo, y devuelve 10 tarjetas (no 0 ni un desafío);
  - acepta `f_TPR` con segundos arbitrarios (`r7200`): todas las tarjetas son de menos de 2 h.

  Si hace falta repetir alguna variante, esperar al menos 30 minutos entre peticiones. Dejar el resultado en `design.md` (sección Migration Plan, paso 3) y fijar `modo` (`or` o `simple`), `max_terminos` y el formato de `f_TPR`. Si algún punto falla, aplicar el respaldo del diseño (§3 y §7) antes de seguir.

## 2. Configuración y base de las fuentes (🟡)

- [x] 2.1 En `config.py` agregar a `Fuente`: `pausa_min_s` y `pausa_max_s` opcionales (misma validación que `Red`) y `ritmo` opcional (`intervalos_min` no vacío y creciente, `limpias_para_bajar ≥ 1`, `tolerancia_min ≥ 0`); a `Red`, `retry_after_max_h` (24). Validar `opciones.consulta` de LinkedIn (`modo` en `or`/`simple`, `max_terminos ≥ 1`, `cola_cada ≥ 2`, `orden`, `margen_min`, `ventana_min_h`). Todo con valores por defecto. Verificar en `test_config.py`: la configuración real carga, una sin los campos nuevos también, y los valores inválidos fallan con un mensaje claro.
- [x] 2.2 En `fuentes/base.py`, usar la pausa propia de la fuente si existe y la de `red` si no. Verificar con una prueba en `test_fuente_base.py`: con una pausa propia de 20–45 s y el rango global de 4–10 s, la pausa pedida al `dormir` inyectado está en 20–45; sin pausa propia, en 4–10.
- [x] 2.3 En `fuentes/base.py`, hacer que `aplicar_cooldown(ahora, minimo_s=None)` use el mayor entre el escalón y `Retry-After` (segundos o fecha HTTP) con el tope `retry_after_max_h`, y que `ejecutar()` lo lea del intento bloqueado. Verificar con los tres escenarios de «El cooldown respeta Retry-After» y con un valor ilegible (se ignora) en `test_fuente_base.py`.

## 3. Ritmo adaptativo (🟡)

- [x] 3.1 Implementar el ritmo en la base de las fuentes, con estado en `kv` (`ritmo:<fuente>:nivel`, `:limpias`, `:ultima`): consulta de «¿toca ya?», subida de nivel en un bloqueo, conteo de peticiones exitosas y bajada de nivel al llegar a `limpias_para_bajar`. Verificar en `test_fuente_base.py` los cuatro escenarios de «Ritmo adaptativo ante bloqueos», incluida la tolerancia (una corrida a los 29 min con intervalo de 30 y tolerancia de 5 sí consulta) y que un dry-run no cambia el estado.
- [x] 3.2 En `Corrida._consultar`, omitir la fuente si el ritmo no permite consultarla, con `resumen.omitidas[nombre] = "ritmo adaptado a N min"`, sin avanzar ninguna rotación. Verificar en `test_buscador.py`: con LinkedIn en nivel 60 y la última petición hace 30 min, la corrida no hace requests a LinkedIn y las demás fuentes se consultan.

## 4. Consultas combinadas y turnos (🟡)

- [x] 4.1 En `config.py`, agregar a `PalabrasClave` los métodos `grupos_nucleo(max)` y `grupos_cola(max)` (cola agrupada por área y partida en trozos; términos entre comillas y unidos por ` OR `; sin repetidos). Verificar en `test_config.py` con la configuración real: 14 términos → 1 grupo con `max=14` y 2 con `max=7`; la cola da un grupo por área y `desarrollo` (16 términos) se parte en dos.
- [x] 4.2 En `rotacion.py`, agregar el cálculo del lote por turnos (design §2): contador `turno`, elección núcleo o cola, recorrido del producto *(grupo × variante)* con contadores propios, `paginas_nucleo` solo para el núcleo, y avance únicamente de lo ejecutado. Verificar en `test_fechas_rotacion.py` (o la prueba de rotación existente): con `cola_cada: 4` y 2 variantes, 8 turnos dan 6 de núcleo y 2 de cola; las variantes alternan; con 2 grupos de núcleo todas las parejas (grupo, variante) aparecen; un turno no ejecutado no avanza nada.
- [x] 4.3 En `Corrida._consultar`, usar el cálculo por turnos cuando `opciones.consulta.modo` sea `or` y `calcular_lote` actual cuando sea `simple` o no exista, y pasar a la fuente `variante_id` y si debe persistir estado (no en dry-run). Verificar en `test_buscador.py`: en modo `or`, una corrida hace una sola petición a LinkedIn con la consulta combinada; en modo `simple`, el comportamiento anterior (con el presupuesto configurado); en dry-run no se mueve ninguna rotación.

## 5. Fuente LinkedIn (🟡)

- [x] 5.1 En `fuentes/linkedin.py` pedir `sortBy` (por defecto `DD`), declarar `soporta_paginas = True` y `tamano_pagina = 10`, y calcular `start = (pagina − 1) × 10`. Verificar en `test_linkedin_computrabajo.py`: los parámetros de la petición incluyen `sortBy=DD` y `start=10` para la página 2, y la prueba existente de parámetros se actualiza.
- [x] 5.2 Calcular `f_TPR` según el último sondeo (design §3): lectura en `kv` por `(variante_id, consulta)`, margen, mínimo `ventana_min_h`, máximo 24 h y ventana de 24 h sin sondeo; la ventana se fija una vez por consulta y corrida, y se reutiliza en la página 2. Verificar con los cuatro escenarios de «Ventana de publicación según el último sondeo» en `test_linkedin_computrabajo.py`.
- [x] 5.3 Registrar el sondeo al terminar la consulta solo si todas sus páginas respondieron bien, con la hora de inicio de la primera petición y nunca en dry-run. Verificar: una consulta con la página 1 buena y la página 2 con 429 deja intacto el sondeo anterior; con ambas buenas, lo actualiza.
- [x] 5.4 Verificar la lectura de la segunda página: con una primera página de 10 vacantes se pide la segunda y no más; con 6, no se pide. Prueba en `test_linkedin_computrabajo.py` con `respx`, y comprobar en ella que entre las páginas se usa la pausa propia.

## 6. Configuración de producción y documentación (🟢)

- [ ] 6.1 Actualizar `config.yaml` (`fuentes.linkedin`): `presupuesto: 2`, `reservado_nucleo: 1`, `paginas_nucleo: 2`, `pausa_min_s: 20`, `pausa_max_s: 45`, `ritmo: {intervalos_min: [30, 60, 120], limpias_para_bajar: 12, tolerancia_min: 5}` y `opciones.consulta` con los valores fijados en la tarea 1.2; `red.retry_after_max_h: 24`. Verificar con `test_config.py` y con `uv run buscador.py --dry-run --fuente linkedin` desde el servidor tras el cooldown (una petición).
- [x] 6.2 Documentar en `README.md` y `deploy/INSTALAR.md` el nuevo ritmo de LinkedIn (peticiones por día, ritmo adaptativo, modos `or` y `simple`) y cómo volver atrás. Verificar releyendo que no queden referencias al presupuesto de 3 ni a la rotación de 2 palabras por corrida.
- [x] 6.3 Correr `ruff check .` y toda la suite (`.venv/Scripts/python -m pytest`), y verificar que solo fallan las 3 pruebas conocidas de Windows.

## 7. Despliegue y verificación en producción (🔴)

- [x] 7.1 Desplegar en `~/buscador-vacantes` (`git pull --ff-only`), confirmar que el timer sigue activo (`systemctl --user list-timers buscador.timer`) y que la siguiente corrida arranca sin errores (`journalctl --user -u buscador -n 50`).
- [ ] 7.2 Verificar a las 24 h con la base del servidor: LinkedIn con ≤ 60 requests en el día y 0 con 429 (`SELECT COUNT(*), SUM(status=429) FROM intentos WHERE fuente='linkedin'`), sin incidente de bloqueo abierto y con más de 40 vacantes de LinkedIn publicadas. A las 48 h: ~70 vacantes al día y la proporción de corridas con página 2. Si hay un 429, comprobar que el ritmo subió un nivel (`kv`: `ritmo:linkedin:nivel`) y que la siguiente petición lleva una ventana que cubre el hueco.
- [ ] 7.3 Marcar la resolución del incidente «LinkedIn · bloqueo» (se cierra solo con la primera respuesta exitosa) y dejar el resultado medido en este archivo. Verificar que `incidentes` no tiene filas abiertas de `linkedin`.
