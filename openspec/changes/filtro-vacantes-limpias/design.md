## Context

Ver `proposal.md` (Why). Estado actual del código en `main`, que es lo que corre producción en `~/buscador-vacantes`:

- `Filtros.evaluar()` (`buscador_vacantes/filtros.py`) aplica, en orden: seniority, antigüedad, geografía (`_geografia`), aceptación (TI en el título + nivel) y rechazo «no TI». Las prácticas nunca se rechazan aquí: siempre pasan a la IA.
- `_geografia()` acepta cualquier lugar de Colombia. Solo mira la modalidad para saber si es remota.
- El campo `modalidad` lo llenan Computrabajo, elempleo y GetOnBoard. Magneto y SPE lo llenan solo cuando es remoto. LinkedIn nunca lo llena.
- La descripción la traen elempleo, Magneto, SPE y GetOnBoard. **LinkedIn y Computrabajo no la traen.**
- `Clasificador` manda a la IA el campo `nivel_filtrado_por_fuente` y guarda una caché por huella sin versión del prompt. El prompt vive en `config.yaml` (`clasificador.prompt_sistema`).
- `categoria_por_terminos()` asigna prácticas con una lista amplia (`sena`, `semillero`, `programa de talento`…). Nadie revisa la categoría que propone la IA.
- `estado.py` tiene `ESQUEMA_VERSION = 1` y un `_migrar_esquema()` que hoy solo crea la versión inicial.
- La tabla `rotacion (fuente, grupo, indice)` ya guarda posiciones circulares por fuente.

## Goals / Non-Goals

**Goals:**
- Que las reglas en código resuelvan todo lo que pueden (ciudad base, call center, prácticas sin TI, lista negra) antes de gastar IA.
- Un único punto de control de la categoría final (el guardarraíl), común a las reglas y a la IA.
- Cambios aditivos en la base: migración automática y sin pérdida, con vuelta atrás sencilla.

**Non-Goals:**
- No se pide el detalle de cada vacante para conseguir su descripción (eso costaría peticiones extra y aumentaría el riesgo de bloqueo).
- No se reestructuran módulos ni se mueve configuración a SQLite.
- No se agrega `/noera` ni ningún comando de Telegram.

## Decisions

### 1. La modalidad se resuelve en `Filtros`, con tres fuentes de verdad en orden
Primero el dato del portal (`vacante.modalidad` normalizado), luego los términos del título y la ubicación, y por último los de la descripción. Hay listas configurables `ubicacion.hibrido` (híbrido, híbrida, hybrid, presencial y remoto, modalidad mixta) y `ubicacion.presencial` (presencial, en sitio, on-site, onsite). Para lo remoto se reutiliza `ubicacion.remoto`.

La descripción solo se usa para detectar remoto o híbrido, nunca presencial: un anuncio híbrido puede decir «presencial dos días».

*Alternativa descartada*: que la IA decida toda la modalidad. Gastaría IA en casos que el portal ya resuelve.

### 2. `_geografia()` devuelve una condición en lugar de un sí o un no
El enum `_Geo` gana dos valores:
- `PRESENCIAL_FUERA`: se rechaza con el nuevo `Motivo.PRESENCIAL_FUERA`.
- `CONFIRMAR_MODALIDAD`: la vacante pasa a dudosa.

La condición viaja con la vacante hasta el clasificador en un campo nuevo, `Vacante.exige_modalidad` (`None`, `"remoto_o_hibrido"` o `"remoto"`). Ese campo no se persiste en `vistas`, pero sí en `vacante_json` (pendientes), para que no se pierda si la IA falla.

Si no hay descripción, se rechaza directamente: es el mismo resultado que daría la IA sin indicio, sin gastar tokens. Esto cubre casi todo LinkedIn (variante ciudad base) y Computrabajo.

La ciudad base se reconoce con la lista `ubicacion.ciudad_base` sobre `ubicacion + titulo`. Los demás municipios de Bolívar no cuentan como base.

### 3. El call center es una regla aparte, dentro del paso de geografía
La lista `filtros.call_center` se compara con el título. Si coincide:
- remoto → sigue la evaluación normal;
- presencial o híbrido → `Motivo.CALL_CENTER`;
- modalidad desconocida → `CONFIRMAR_MODALIDAD` con `exige_modalidad = "remoto"`, o rechazo si no hay descripción.

Va antes de la regla de ciudad base, para que también aplique en Cartagena.

*Alternativa descartada*: poner a KONECTA en la lista negra. Bloquearía también sus vacantes remotas, que el dueño sí quiere.

### 4. La lista negra es el primer paso de `evaluar()`
`filtros.lista_negra.empresas` se compara con la empresa normalizada (sin sufijos societarios, con la misma función de la huella) por inclusión. `filtros.lista_negra.palabras` se compara con el título. Motivo: `Motivo.LISTA_NEGRA`. Las dos listas empiezan vacías.

### 5. Prácticas sin TI: solo se rechazan tras leer la descripción
La excepción del paso 5 de `evaluar()` (`not coincidencias(self._practica, titulo)`) se conserva para las vacantes sin descripción y se agrega un rechazo explícito: si el título tiene un término de práctica, **la vacante trae descripción** y ni el título ni la descripción tienen TI (áreas o `ti_generico`), se rechaza con `Motivo.NO_TI` y el detalle «práctica sin TI». Si la descripción sí tiene TI, o no hay descripción (LinkedIn y Computrabajo), sigue a la IA como hoy: sin descripción no hay con qué afirmar que no es TI.

### 6. El guardarraíl es una función pura que se llama en un solo lugar
La función es `Filtros.guardarrail_practicas(vacante) -> Correccion | None`:
- revisa la evidencia con `nivel.evidencia_practica` (título) y `nivel.evidencia_practica_descripcion` (descripción, solo términos fuertes);
- recategoriza con `categoria_por_area()` o, si no coincide ningún área, con `OTROS_TI`;
- rechaza si tampoco hay TI.

`Corrida` la aplica sobre `aceptadas_reglas + aceptadas por la IA`, justo antes de armar `a_publicar`, y cuenta `practicas_recategorizadas` y `practicas_rechazadas` en `ResumenCorrida`. Así no importa de dónde vino la categoría.

*Alternativa descartada*: corregir dentro del clasificador. Dejaría sin revisar lo que aceptan las reglas.

### 7. La versión del prompt es un hash
`version_prompt = sha256(prompt_sistema)[:12]`. Se guarda en una columna nueva, `clasificaciones.version_prompt`. `_cache()` solo devuelve filas con la versión vigente y `_guardar_clasificacion()` la escribe. Las filas viejas (`NULL`) quedan como historial para consultas, sin reutilizarse.

*Alternativa descartada*: borrar `clasificaciones` en la migración. Se perdería el historial que usa el diagnóstico.

### 8. Payload de la IA
- Se elimina `nivel_filtrado_por_fuente`, y con él el parámetro `fuentes_con_filtro_nivel` del clasificador y su cálculo en `Corrida._clasificar`.
- Se agregan `ciudad_base` (texto) y `exige_modalidad`.
- `filtra_nivel` sigue en `config.yaml`, pero solo como documentación de la fuente.

El prompt se reescribe con las reglas del spec: hasta 1 año, salario solo como apoyo, modalidad exigida y sin excepción para el SENA genérico. Se suben los `TOKENS_POR_VACANTE` solo si las pruebas muestran respuestas cortadas.

### 9. Variantes de LinkedIn mediante la rotación existente
`fuentes.linkedin.opciones.variantes` es una lista de dicts con parámetros de petición y una `modalidad` opcional. Ejemplo:

```yaml
variantes:
  - {location: Colombia, f_WT: "2,3", modalidad: "Remoto o híbrido"}
  - {location: "Cartagena, Bolívar, Colombia"}
```

`Corrida._consultar` lee el índice con `rotacion.obtener_indice(estado, "linkedin", "variante")`, se lo pasa a la fuente (`fuente.variante = ...`) y avanza el índice al final. La fuente combina la variante con sus `opciones` en `construir_peticion` y aplica su `modalidad` en `parsear`. Si `variantes` no existe, el comportamiento es el actual: así se mantiene la compatibilidad y las pruebas existentes.

*Alternativa descartada*: alternar la variante por petición dentro de la misma corrida. Con 3 peticiones repartiría mal las palabras clave del núcleo.

### 10. Esquema 2 con `ALTER TABLE ADD COLUMN`
Columnas nuevas:
- `vistas`: `ubicacion` y `modalidad`;
- `clasificaciones`: `version_prompt`;
- `corridas`: `practicas_recategorizadas` y `practicas_rechazadas`, ambas `INTEGER NOT NULL DEFAULT 0`.

`_migrar_esquema()` pasa de la versión 1 a la 2 dentro de una transacción. El código actual se niega a abrir una base con un esquema más nuevo (`RuntimeError`), así que volver atrás exige restaurar el respaldo o bajar `esquema_version` a 1. Las columnas nuevas no estorban al código anterior.

### 11. Métricas
- `DESCARTES` gana `LISTA_NEGRA`, `PRESENCIAL_FUERA` y `CALL_CENTER`, con sus nombres en `NOMBRES_DESCARTE`.
- `resumen.calcular_metricas` suma las dos columnas nuevas de `corridas`.
- `componer_resumen` agrega la línea «🛡️ Guardarraíl de prácticas: N recategorizadas · M rechazadas».
- Las mismas cifras se agregan a `para_ia()`, para que las recomendaciones las vean.

## Risks / Trade-offs

- [Caída fuerte del volumen publicado: LinkedIn sin descripción y Computrabajo sin modalidad pierden muchas vacantes de otras ciudades] → Es el comportamiento pedido. El resumen diario muestra cuántas descarta cada regla. Si una fuente queda casi vacía, se evalúa pedir el detalle en un change aparte.
- [Remotas que el portal no marca como remotas y que no traen descripción se rechazan] → Se acepta. La variante remoto o híbrido de LinkedIn y las etiquetas de Computrabajo cubren la mayoría.
- [LinkedIn podría ignorar `f_WT` o cambiar sus valores] → Una prueba con fixture verifica el parámetro enviado. Si LinkedIn deja de filtrar, la modalidad «Remoto o híbrido» sería falsa. Mitigación: en la verificación manual (tarea 8) se revisa una muestra real.
- [Más llamadas a la IA por las dudosas de modalidad] → Solo pasan las que traen descripción. El presupuesto diario `ia.presupuesto_dia` sigue limitando, y la caché por versión evita repetir.
- [Conflictos al unir con `asistente-postulacion-telegram` en `config.yaml`, `corrida.py` y `resumen.py`] → Los cambios de esa rama son en otras secciones (asistente, destino de avisos). Se resuelven al integrar; se anota en tasks.
- [Un falso negativo de la ciudad base, por ejemplo «Bolívar» sin ciudad] → La lista es configurable. «Bolívar» solo no cuenta como base, para no aceptar Magangué presencial.

## Migration Plan

1. Implementar en la rama `filtro-vacantes-limpias`, que sale de `main`, con las pruebas en verde.
2. Verificar con `--dry-run` en una copia aparte del Fedora (no en `~/buscador-vacantes`) usando una copia de `data/vacantes.db`, y revisar las vacantes que se publicarían.
3. Con el visto bueno del dueño: unir a `main`, respaldar `data/vacantes.db` en el Fedora (`cp data/vacantes.db data/vacantes.db.antes-filtro`) y hacer `git pull --ff-only` en `~/buscador-vacantes`. El timer toma el código en la siguiente corrida y la base migra sola.
4. **Vuelta atrás**: `git checkout <commit anterior>` en `~/buscador-vacantes` y además, porque el código viejo rechaza el esquema 2, una de dos: restaurar `data/vacantes.db.antes-filtro` (se pierden las vistas posteriores, con riesgo de repetir alguna publicación) o ejecutar `UPDATE esquema_version SET version = 1` (se conservan los datos y el código viejo ignora las columnas nuevas). Se prefiere la segunda.
5. Revisar el resumen diario del día siguiente y el grupo durante 2 o 3 días.
