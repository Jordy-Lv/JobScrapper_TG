# Proposal

## Why

La prioridad del grupo «JOBS - PRÁCTICAS/APRENDIZ» es encontrar **todas** las vacantes de aprendizaje, contrato de aprendizaje SENA, prácticas y pasantías de TI. Hoy pasan cuatro cosas:

- **Se pierden vacantes.** El dueño encuentra a mano vacantes de aprendizaje que el bot no publicó, y no hay forma de saber por qué: las vacantes rechazadas no quedan registradas en ninguna parte.
- **El nivel junior gasta presupuesto.** Más de la mitad de la cola larga de búsqueda son consultas junior que no son la prioridad actual.
- **El canal tiene ruido.** Cada mensaje del canal lleva un botón ⚡ por vacante.
- **Todas las ofertas se ven igual.** La que cumple todo lo que busca el dueño tiene el mismo formato que la que pasó justo.

Además, el bot asistente solo sirve para postularse: no permite consultar las ofertas ya publicadas.

## What Changes

**1. Elegir la vacante con menos ruido**
- Cada mensaje de ofertas del canal lleva **un solo botón**, «⚡ Postularme a una de estas», en lugar de un botón por vacante.
- El botón abre el bot asistente en privado con un **selector**: una sola tarjeta editable con las vacantes de ese mensaje, numeradas y paginadas. Al elegir una vacante sigue el flujo de postulación de siempre.
- Si el usuario aún no terminó el registro, el lote de vacantes queda pendiente y el selector aparece al terminar.

**2. Aprendizaje primero; junior listo pero apagado**
- Nuevo interruptor `alcance.junior` en `config.yaml`, **apagado por defecto**. Mientras está apagado:
  - no se buscan las palabras clave junior (pasan a su propio grupo);
  - el código descarta las vacantes aceptadas en un área junior, con el motivo `nivel_pausado`;
  - el prompt del clasificador describe solo prácticas y aprendizaje.

  Al encenderlo vuelve todo el comportamiento junior, sin tocar código. **BREAKING**: el canal deja de publicar vacantes junior.
- **Auditoría de descartes:** cada vacante rechazada (por reglas, por la IA, por el guardarraíl o por el nivel pausado) queda en una tabla `descartes` con su motivo, por 14 días.
- **Diagnóstico de vacantes:** nuevo comando `buscador.py diagnosticar <url | título>`. Le dice al dueño si la vacante se buscó, si llegó, qué regla o qué respuesta de la IA la rechazó y por qué.
- **Revisión exhaustiva de las reglas**, con un corpus de vacantes de aprendizaje reales que el bot perdió. Hipótesis encontradas leyendo el código, que se confirman o descartan con ese corpus:
  - los años de la empresa ("más de 20 años de experiencia en el sector") se cuentan como experiencia exigida;
  - una práctica con un término de seniority en el título se rechaza sin pasar por la IA;
  - «práctica sin TI» se rechaza mirando solo un fragmento corto de la descripción (elempleo y Magneto);
  - «SENA», «semillero» y «programa de talento» no cuentan como evidencia de práctica para el guardarraíl;
  - la republicación de la misma vacante por la misma empresa (nueva cohorte de aprendices) se descarta como duplicada durante 90 días;
  - las dudosas se pierden si DeepSeek falla 24 h seguidas.
- **Búsqueda:**
  - «contrato de aprendizaje», «etapa productiva» y las variantes por rol (aprendiz o practicante de desarrollo, soporte, redes, datos) pasan al núcleo;
  - el presupuesto que liberan las consultas junior va al núcleo de aprendizaje.
- **DeepSeek verificable:**
  - comando `buscador.py ia --verificar`: comprueba la clave y el saldo, y mide los aciertos contra un conjunto de casos etiquetados;
  - nuevo incidente `ia:clasificador`, por saldo bajo, corridas seguidas sin respuesta válida o dudosas vencidas;
  - métricas de la IA en el resumen diario;
  - una dudosa con evidencia fuerte de práctica de TI no se descarta solo porque la IA no respondió.

**3. Protagonismo para las ofertas que cumplen los filtros principales**
- Una vacante es **destacada** si cumple los criterios configurables de `publicacion.destacadas`. Por defecto:
  - nivel de práctica o aprendizaje explícito en el título;
  - área de TI identificada;
  - en Cartagena o remota;
  - publicada hace 3 días o menos.
- Las destacadas abren el mensaje en un bloque «⭐ DESTACADAS», con la ficha completa y una línea que dice qué criterios cumple. Las demás van en formato compacto, de una o dos líneas.

**4. Consultas de ofertas desde el bot asistente**
- Nuevo comando `/buscar` y botón «🔎 Buscar vacantes» en la ayuda del bot. Abren una tarjeta de filtros con botones: nivel, área, modalidad, antigüedad, fuente y solo destacadas.
- Los resultados se paginan y cada uno se puede elegir para postularse, con el mismo selector del punto 1.
- **Búsqueda con tus palabras:** `/buscar remotas de Python de esta semana`. DeepSeek solo traduce el texto a filtros de una lista cerrada, y el código hace la consulta. La IA nunca inventa ni elige vacantes.
  - Tiene un tope diario por usuario.
  - Sin IA, el texto se usa como búsqueda en el título.
- Mientras `alcance.junior` esté apagado, el filtro «Junior» aparece como pausado.

**Fuera de alcance:**
- alertas personalizadas («avísame cuando salga…»);
- filtros guardados;
- fuentes nuevas;
- cambios en la extensión del navegador.

## Capabilities

### New Capabilities

- `selector-vacantes-asistente`: el botón único del canal, el enlace al bot con el lote de vacantes y la tarjeta de selección paginada.
- `consultas-vacantes-asistente`: el comando `/buscar`, la tarjeta de filtros, los resultados paginados y la traducción del texto libre a filtros con DeepSeek.
- `auditoria-descartes`: el registro de cada vacante rechazada con su motivo y el comando de diagnóstico.

### Modified Capabilities

Estas capacidades todavía no están en `openspec/specs/`: nacen al archivar `crear-buscador-vacantes` y se amplían en otros changes abiertos. Por eso sus deltas solo usan `ADDED`, igual que en `linkedin-detalle-vacantes`.

- `filtrado-vacantes`: el nivel junior queda pausado y configurable, se corrigen las reglas que pierden prácticas, el guardarraíl acepta más evidencia y cambia la política ante una IA caída.
- `busqueda-fuentes`: el grupo de palabras clave junior solo se busca con el nivel activo y el núcleo de aprendizaje crece.
- `publicacion-telegram`: hay vacantes destacadas, el formato compacto para las demás y un solo botón por mensaje.
- `deduplicacion-estado`: se guarda el lote de cada mensaje publicado y se permite republicar a una empresa que vuelve a publicar la misma vacante.
- `incidentes-reportero`: incidente `ia:clasificador`.
- `resumen-diario`: métricas de la IA, de los descartes por nivel pausado y de las destacadas.

## Impact

- **Radar:**
  - `buscador_vacantes/radar/filtros.py`: reglas de experiencia, seniority en prácticas, «práctica sin TI» con descripción completa y nivel pausado.
  - `clasificador.py`: prompt armado por nivel y política ante una IA caída.
  - `corrida.py`: registro de descartes y nivel pausado.
  - `formato.py` y `publicacion.py`: destacadas, formato compacto y botón único.
  - `incidentes.py` y `resumen.py`.
  - Comandos nuevos en `buscador.py`: `diagnosticar` e `ia --verificar`.
- **Común:**
  - `comun/config.py`: `alcance`, `publicacion.destacadas`, `palabras_clave.junior` y `estado.republicar_tras_dias`.
  - `comun/estado.py`: tablas `descartes` y `lotes_canal`, con migración de esquema.
- **Asistente:**
  - `asistente/conversacion.py`, o el paquete que deje `dividir-conversacion-asistente` si se aplica antes: selector y `/buscar`.
  - `asistente/vacantes.py`: el índice gana ubicación, modalidad, publicada y destacada.
  - `asistente/datos.py`: migración del esquema 3.
  - `asistente/textos.py`.
- **Configuración:** `palabras_clave`, `alcance`, `filtros.nivel.evidencia_practica`, `clasificador`, `publicacion`, `estado` y `asistente.consultas` de `config.yaml`.
- **Pruebas:** `tests/radar/test_filtros.py`, `test_casos_reales.py` (más un corpus nuevo de aprendizaje), `test_formato.py`, `test_publicacion.py`, `test_clasificador.py`, `test_incidentes.py`, `test_resumen.py` y `tests/asistente/test_bot.py`.
- **Producción (Fedora):**
  - `git pull` y reinicio de `buscador-asistente`.
  - Las migraciones de `vacantes.db` y `asistente.db` son aditivas.
  - Al cambiar el prompt cambia su versión y la caché de clasificaciones se renueva sola.
  - El canal deja de recibir vacantes junior desde la primera corrida.
- **Costo de IA:** la traducción de consultas usa la clave DeepSeek del servidor, con tope diario. El clasificador deja de gastar en vacantes junior.
