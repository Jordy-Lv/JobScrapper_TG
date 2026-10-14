## 1. Configuración, modelo y esquema (🟡)

- [x] 1.1 Agregar a `config.py` el modelo opcional `Fuente.detalle` (`activo`, `max_por_corrida`, `pausa_min_s`, `pausa_max_s`, `max_caracteres`, `horas_vencimiento`, `espera_reintento_min`, con los valores por defecto del design §2) y llenar `fuentes.linkedin.detalle` en `config.yaml` con comentarios. Verificar con `test_config.py`: la configuración real carga, una sin `detalle` también y un valor inválido (por ejemplo `max_por_corrida: -1`) indica el campo.
- [x] 1.2 Migrar `estado.py` al esquema 3 según design §5: tablas `pendientes_detalle` y `detalles`, columnas `detalles_*` en `corridas`, migración 2 → 3 que ignora columnas existentes y `limpiar()` para las dos tablas nuevas. Verificar en `test_estado.py`: una base del esquema 2 con datos migra a 3 sin perder filas, una base nueva nace en 3, volver a migrar tras bajar la versión no falla, y `limpiar()` borra lo viejo.
- [x] 1.3 Agregar a `estado.py` las operaciones de la cola y la caché: agregar a la cola sin duplicar, listar las que ya cumplieron su `proximo_intento` de la más antigua a la más reciente, registrar un fallo (sube `intentos`, fija `proximo_intento` y `ultimo_error`), quitar, vencer, y guardar y leer un detalle. Verificar en `test_estado.py`, incluido que una oferta repetida no se duplica y que lo guardado sobrevive a reabrir la base.

## 2. Lectura del detalle en LinkedIn (🟡)

- [x] 2.1 Crear `tests/fixtures/linkedin_detalle.html` recortando una respuesta real de `jobs-guest/jobs/api/jobPosting/{id}` (con el bloque de descripción, sin datos personales) y otra sin bloque reconocible. Implementar `recortar_descripcion()` según design §7 (texto limpio, primeros N caracteres y frases de modalidad posteriores). Verificar con pruebas: el recorte respeta el máximo, conserva una frase «100% remoto» que está al final y no parte palabras.
- [x] 2.2 Implementar `Fuente.obtener_detalle()` (no soportado por defecto) y `LinkedIn.obtener_detalle()` según design §1, con los resultados `OK`, `CERRADA`, `BLOQUEADA` y `FALLO`, registro del intento y `CAMBIO_HTML` para un 200 sin descripción. Verificar en `test_linkedin_computrabajo.py` con respx: 200 con texto, 404, 429 con `Retry-After`, error de servidor, tiempo agotado y 200 sin bloque.
- [x] 2.3 Aplicar el cooldown en el detalle: un `BLOQUEADA` llama a `aplicar_cooldown` (con `Retry-After`) y actualiza el ritmo, igual que un bloqueo de búsqueda. Verificar con una prueba: tras un 429 de detalle, `cooldown_vigente` devuelve la hora y la siguiente búsqueda se omite.

## 3. Reglas del filtro (🟡)

- [x] 3.1 Agregar `Motivo.PENDIENTE_DETALLE` y `Evaluacion` para la oferta pendiente, y el parámetro `permite_detalle` en `Filtros.evaluar()` según design §3. Verificar en `test_filtros.py` con los escenarios de «Ofertas pendientes de detalle»: remota de otra ciudad queda pendiente, título sin TI se rechaza sin detalle, call center sin modalidad queda pendiente, lo declarado presencial se rechaza sin detalle y, con `permite_detalle=False`, todo sigue como hoy.
- [x] 3.2 Hacer que `_modalidad()` informe el origen de la señal y que, para las fuentes con detalle, remoto o híbrido visto solo en la descripción dé `CONFIRMAR_MODALIDAD` (design §4). Verificar con los escenarios de «La modalidad que solo sale del detalle la confirma la IA» y comprobando que Computrabajo, elempleo y Magneto no cambian.
- [x] 3.3 Ajustar el prompt del clasificador en `config.yaml` (el indicio de remoto debe ser la modalidad del puesto, no la de la empresa o el equipo) y recortar la descripción que se envía a 1500 caracteres con `recortar_descripcion()`. Verificar en `test_clasificador.py` que el payload trae la descripción recortada con la frase de modalidad y que el prompt cargado contiene la regla nueva.

## 4. Corrida (🟡)

- [x] 4.1 En `Corrida._evaluar()`, evaluar con `permite_detalle` según la fuente: usar la caché `detalles` cuando exista, encolar sin duplicar contra la cola y `vistas`, y contar la oferta como cruda una sola vez. Verificar en `test_buscador.py` con una corrida simulada (respx): una oferta de LinkedIn de Bogotá sin modalidad queda en la cola y no cuenta como descarte, y la misma oferta en la corrida siguiente no se duplica.
- [x] 4.2 Implementar `Corrida._resolver_detalles()` según design §6: vencimiento, cooldown y ritmo, presupuesto, pausa, orden de la más antigua a la más reciente, y las salidas `OK`, `CERRADA`, `FALLO` y `BLOQUEADA`, reevaluando e integrando lo recuperado a `aceptadas_reglas` y `dudosas`. Verificar en `test_buscador.py`: con presupuesto 2 y 5 en cola solo se piden 2 (las más antiguas); un 429 corta el paso, deja la cola intacta y aplica el cooldown; una oferta de Medellín con «100% remoto» en el detalle llega a la IA con la condición y una con «presencial» se rechaza; un 404 sale como cerrada; el fallo reintenta tras la espera.
- [x] 4.3 Verificar que ninguna oferta se pierde: simular una corrida interrumpida entre pedir el detalle y evaluarlo, y una oferta con más de `horas_vencimiento`. Verificar que la primera sigue en la cola y que la segunda sale como vencida con un registro en el log y en el contador.
- [x] 4.4 Contar `detalles_pedidos`, `detalles_fallidos`, `detalles_recuperadas`, `detalles_cerradas` y `detalles_vencidas` en `ResumenCorrida`, en `linea_log()` y en `_guardar_corrida()`. En `--dry-run`, listar las ofertas que irían a detalle sin pedirlas ni tocar la cola; en `--seed`, registrarlas como vistas. Verificar con pruebas de dry-run y de siembra.

## 5. Resumen diario (🟡)

- [x] 5.1 Sumar las cifras de detalle en `resumen.py` (`calcular_metricas`, `componer_resumen` y `para_ia`), con la cola actual leída de `pendientes_detalle`. Verificar en `test_resumen.py` que aparece la línea «Detalle de LinkedIn: N pedidos · M fallidos · K recuperadas · C en cola · V vencidas» y que las cifras llegan a los datos de la IA.

## 6. Regresión con casos reales y documentación (🟡)

- [x] 6.1 Agregar a `tests/fixtures/casos_reales_2026-10.yaml` los casos de LinkedIn que ahora quedan pendientes («Analista Desarrollo Web Proyecto 6 Meses» de Los Olivos Bogotá, «Software Engineer Intern» de Sezzle, «Programador Junior- Data Engineering» de Inetum) y ajustar `tests/test_casos_reales.py` para evaluar con `permite_detalle`. Verificar que Los Olivos con un detalle que dice «presencial» se rechaza y que Sezzle con un detalle que dice «100% remoto» pasa a la IA.
- [x] 6.2 Correr la suite completa (`.venv/Scripts/python -m pytest`, y en el Fedora para las pruebas que usan `fcntl`) y `ruff check`. Verificar que todo pasa, salvo las 3 pruebas propias de Windows que ya fallaban.
- [x] 6.3 Actualizar `README.md`, los comentarios de `config.yaml` y `deploy/INSTALAR.md` (detalle de LinkedIn, cola, vencimiento, cómo apagarlo con `detalle.activo: false` y la vuelta atrás). Verificar que no queda ninguna mención a que LinkedIn «no puede dar la modalidad».

## 7. Verificación y despliegue (👤 con apoyo)

- [ ] 7.1 Ejecutar `uv run buscador.py --dry-run` en una copia aparte del Fedora, con una copia de `data/vacantes.db` y sin tocar `~/buscador-vacantes`. Verificar que lista las ofertas de LinkedIn que irían a detalle y no hace ninguna petición de detalle.
- [x] 7.2 👤 Con el visto bueno del dueño: respaldar `data/vacantes.db` en el Fedora, unir `linkedin-detalle-vacantes` a `main` y hacer `git pull --ff-only` en `~/buscador-vacantes`. Verificar en el log de la siguiente corrida que la base quedó en el esquema 3, que se pidieron detalles y que no hubo bloqueos.
- [ ] 7.3 👤 Revisar el grupo y el resumen diario durante 2 o 3 días. Verificar que llegan ofertas remotas de LinkedIn, que ninguna presencial de otra ciudad se cuela, que la cola no crece sin tope y que el 429 no se repite; si se bloquea, bajar `max_por_corrida`.
- [ ] 7.4 🟢 Archivar este change después de `filtro-vacantes-limpias` y `linkedin-peticiones-eficientes`. Sus deltas usan `ADDED` y complementan specs que solo existen al archivar esos changes. Verificar que `openspec archive linkedin-detalle-vacantes` termina sin rechazos.
