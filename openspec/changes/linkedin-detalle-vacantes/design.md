## Context

Estado del código en `main` (producción corre `main` en `~/buscador-vacantes`), tras `filtro-vacantes-limpias` y `linkedin-peticiones-eficientes`:

- `Filtros._geografia()` rechaza con `PRESENCIAL_FUERA` una oferta de otra ciudad sin modalidad ni descripción, y con `CALL_CENTER` un puesto de call center sin modalidad ni descripción. Con descripción, las mismas situaciones pasan a dudosa con `exige_modalidad`.
- LinkedIn nunca trae modalidad ni descripción: sus tarjetas solo dan título, empresa, ubicación, fecha y a veces salario. Los demás portales con descripción (elempleo, Magneto, SPE, GetOnBoard) la traen en el listado.
- `Fuente` (base) ya tiene cooldown con `Retry-After`, ritmo adaptativo, registro de intentos y `_hacer_request()`. `Corrida._consultar()` crea una instancia de la fuente por corrida y la cierra al terminar.
- `Corrida._evaluar()` evalúa cada vacante una vez; las aceptadas por reglas y las dudosas siguen a la IA. `Clasificador` ya guarda pendientes con vencimiento (`pendientes`) y `Estado` tiene `por_enviar` para lo que no se pudo enviar.
- La rama del asistente de postulación tiene un lector de detalle (`asistente/detalle.py`, asíncrono, sobre su propia base) que reconoce el bloque de descripción de LinkedIn con `div.description__text, section.show-more-less-html`. No está en `main`.
- Comprobado el 2026-10-14 con peticiones reales: `GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}` respondió 200 en 3 de 3 con la descripción completa (40 a 66 KB), sin campo estructurado de modalidad. `/jobs/view/{id}` dio 429 a la tercera petición seguida.

## Goals / Non-Goals

**Goals:**
- Recuperar las ofertas remotas de LinkedIn sin dejar pasar presenciales de otras ciudades.
- Que ninguna oferta se pierda por un fallo transitorio: todo fallo deja la oferta en una cola persistente.
- No aumentar de forma notable el riesgo de bloqueo de LinkedIn.
- Reutilizar las reglas de modalidad y la IA que ya existen; no crear un segundo camino de decisión.

**Non-Goals:**
- No iniciar sesión en LinkedIn, ni evadir captchas, ni usar proxies.
- No pedir detalle de las ofertas que las reglas del título ya rechazan, ni de las de la ciudad base, ni de las que dicen «remoto» en el título.
- No pedir detalle de otros portales (traen descripción o etiqueta de modalidad en el listado).
- No compartir código con el asistente de postulación hasta que su rama se integre.

## Decisions

### 1. El detalle sale del endpoint de invitados `api/jobPosting/{id}`
`LinkedIn.obtener_detalle(vacante)` pide `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id_fuente}` con el cliente HTTP de la fuente (`_hacer_request`) y extrae el texto del bloque `div.description__text` o `section.show-more-less-html`. Cada petición se registra como un intento de la fuente (con `keyword = "detalle <id>"`), así que cuenta en `requests_por_fuente` y en los incidentes.

Resultados posibles: `OK` con texto; `CERRADA` (404 o 410); `BLOQUEADA` (403, 429, 999 o desafío, con `Retry-After` si viene); `FALLO` (tiempo agotado, error de servidor o un 200 sin bloque de descripción reconocible, que además se registra como `CAMBIO_HTML` para que el detector de incidentes lo vea).

*Alternativas descartadas*: la página `/jobs/view/{id}` (300 KB, y dio 429 en las pruebas); iniciar sesión (viola las restricciones del proyecto); depender de `asistente/detalle.py` (no está en `main`, es asíncrono y usa otra base).

### 2. Configuración por fuente
`fuentes.<nombre>.detalle` (modelo pydantic opcional; sin él, la fuente no pide detalle):

```yaml
detalle:
  activo: true
  max_por_corrida: 6        # peticiones de detalle por corrida
  pausa_min_s: 6            # pausa propia del detalle, más lenta que la de la búsqueda
  pausa_max_s: 12
  max_caracteres: 3000      # recorte de la descripción guardada
  horas_vencimiento: 48     # espera máxima en la cola
  espera_reintento_min: 30  # tras un fallo, espera de 30 × intentos minutos
```

Con 48 corridas al día y 6 detalles por corrida, el tope es de 288 peticiones al día. La búsqueda de LinkedIn usa 1 a 3 por corrida. Se parte de un presupuesto bajo y el resumen diario avisa si la cola crece.

### 3. `Filtros` distingue «falta información» de «es presencial»
`evaluar(vacante, ahora, *, permite_detalle=False)`. Con `permite_detalle=True` (la fuente tiene detalle activo y la oferta aún no tiene descripción), los dos rechazos que nacen de no saber la modalidad (`PRESENCIAL_FUERA` por «sin modalidad» y `CALL_CENTER` por «sin modalidad ni descripción») no se devuelven: `_geografia()` responde `PENDIENTE_DETALLE` y el resto de las reglas siguen evaluando el título (seniority, antigüedad, TI, áreas no TI). Si el resto rechaza, se devuelve ese rechazo, y así no se gasta una petición en una oferta sin TI. Si el resto aceptaría o dejaría en duda, se devuelve `Evaluacion(DUDOSA, Motivo.PENDIENTE_DETALLE)` con la condición de modalidad que corresponde. Lo presencial declarado («Presencial» en el título o la ubicación) sigue rechazándose sin detalle.

### 4. La modalidad que solo sale del detalle la confirma la IA
`_modalidad()` devuelve también de dónde salió la señal (portal, título y ubicación, o descripción). Para las fuentes con detalle, si remoto o híbrido solo se vio en la descripción, `_geografia()` devuelve `CONFIRMAR_MODALIDAD` (con «remoto o híbrido», o «solo remoto» en call center) en lugar de `OK`. Así una mención suelta de «equipos remotos» no acepta una oferta presencial por reglas, que es el fallo que se quiere evitar. Se ajusta el prompt del clasificador: el indicio de remoto vale solo si describe la modalidad del puesto y no la de la empresa o del equipo.

### 5. Cola persistente y caché en el esquema 3
Tablas nuevas, además de columnas en `corridas`:

- `pendientes_detalle(clave PK, huella, vacante_json, desde, intentos INTEGER DEFAULT 0, proximo_intento TEXT, ultimo_error TEXT)`.
- `detalles(clave PK, texto, ts)`: la descripción ya obtenida. Se reutiliza si la oferta reaparece. `limpiar()` la borra a los `max_dias_publicada` días, y borra también las entradas de la cola con más de `dias_intentos` días como red de seguridad.
- `corridas`: `detalles_pedidos`, `detalles_fallidos`, `detalles_recuperadas`, `detalles_cerradas` y `detalles_vencidas`, todas `INTEGER NOT NULL DEFAULT 0`.

La migración 2 → 3 sigue el patrón de la 1 → 2: `CREATE TABLE IF NOT EXISTS` y `ALTER TABLE ADD COLUMN` que ignora columnas ya existentes. Volver atrás exige bajar `esquema_version` a 2; el código anterior ignora las tablas y columnas nuevas.

### 6. Flujo de la corrida
1. `_evaluar()` evalúa con `permite_detalle` según la fuente. Una oferta con `PENDIENTE_DETALLE` primero se compara con la caché `detalles`: si ya hay texto, se asigna a `descripcion` y se vuelve a evaluar sin más. Si no, y no está ya en la cola ni en `vistas`, se agrega a la cola. Cuenta como cruda una sola vez.
2. Un paso nuevo `_resolver_detalles()` corre después de `_evaluar()` y antes de la IA:
   - borra de la cola y registra (log y contador) las que superan `horas_vencimiento`;
   - si LinkedIn está en cooldown o en ritmo adaptado, no pide nada y las ofertas esperan;
   - toma de la cola, de la más antigua a la más reciente, las que ya cumplieron su `proximo_intento`, hasta `max_por_corrida`, con la pausa entre peticiones;
   - con `OK`: guarda el texto en `detalles`, quita la oferta de la cola, le asigna la descripción y la evalúa de nuevo con todas las reglas. Lo que queda aceptado o dudoso se agrega a `aceptadas_reglas` o `dudosas` y sigue el flujo normal, incluida la IA; lo rechazado se cuenta en sus descartes;
   - con `CERRADA`: la quita y la cuenta como cerrada;
   - con `FALLO`: sube `intentos`, guarda el error y fija `proximo_intento` en `30 × intentos` minutos;
   - con `BLOQUEADA`: aplica el cooldown de la fuente (como un bloqueo de búsqueda), deja la oferta como estaba y corta el paso.
3. La oferta sale de la cola solo después de que su resultado se registró (un `with estado.transaccion()` por oferta), de modo que una corrida interrumpida no pierde nada.
4. En `--dry-run` se listan las ofertas que irían a detalle, sin pedirlas ni tocar la cola. En `--seed` las candidatas se registran como vistas, para que la siembra no deje ofertas viejas que luego se publiquen todas juntas.

### 7. Recorte de la descripción que conserva la modalidad
`recortar_descripcion(texto, maximo)` conserva los primeros `maximo` caracteres y añade, hasta 1000 más, las frases posteriores que contengan términos de modalidad (los de `ubicacion.remoto`, `ubicacion.hibrido` y `ubicacion.presencial`). Así lo que decide la modalidad no se pierde si está al final del anuncio. El clasificador recibe la descripción recortada a 1500 caracteres con el mismo criterio, para acotar los tokens de un lote de 30.

### 8. Orden y métricas
La cola se atiende de la más antigua a la más reciente para que ninguna oferta quede relegada. Una oferta recuperada es la que tras el detalle sigue como aceptada o dudosa. El resumen diario suma una línea de detalle y la cola actual se lee de `pendientes_detalle`.

## Risks / Trade-offs

- [LinkedIn bloquea por las peticiones de detalle] → Presupuesto bajo, pausa de 6 a 12 s, cooldown compartido con la búsqueda (un 429 corta los detalles y la búsqueda siguiente espera), respeto de `Retry-After` y ritmo adaptativo. Si aun así se bloquea, se baja `max_por_corrida`. Nada se pierde: la cola espera.
- [Remotos falsos por menciones sueltas] → La modalidad que solo viene del detalle siempre pasa por la IA, con el prompt ajustado. Costo: más llamadas de IA, acotadas por `ia.presupuesto_dia`.
- [La cola crece más rápido de lo que se vacía] → El resumen diario lo muestra y sugiere subir el presupuesto. Al vencer a las 48 h la oferta sale de la cola con aviso en el log y en el resumen, nunca en silencio. Esto es el único caso en que una oferta puede no resolverse.
- [LinkedIn cambia el HTML del detalle] → Un 200 sin bloque reconocible se registra como `CAMBIO_HTML` (incidente), cuenta como fallo y deja la oferta en cola; las ofertas vencen visiblemente en vez de rechazarse.
- [Retraso de unos minutos hasta que una oferta llega al canal] → Se acepta: se resuelve en la misma corrida si el presupuesto alcanza, y si no, en las siguientes.
- [Más tokens por lote de la IA] → Recorte a 1500 caracteres por oferta en el payload.

## Migration Plan

1. Implementar en la rama `linkedin-detalle-vacantes`, que sale de `main`, con las pruebas en verde (fixtures recortados de respuestas reales de LinkedIn).
2. Probar con un `--dry-run` en una copia aparte del Fedora, con una copia de `data/vacantes.db`: debe listar las ofertas de LinkedIn que irían a detalle.
3. Con el visto bueno del dueño: respaldar `data/vacantes.db` y hacer `git pull --ff-only` en `~/buscador-vacantes`. La base migra sola al esquema 3 en la siguiente corrida.
4. Revisar el log de las primeras corridas: detalles pedidos, bloqueos y cola. Revisar el grupo y el resumen diario durante 2 o 3 días.
5. **Vuelta atrás**: `git checkout <commit anterior>` y `UPDATE esquema_version SET version = 2` (los datos se conservan). Como remedio rápido sin tocar el código, poner `fuentes.linkedin.detalle.activo: false`: las ofertas sin modalidad vuelven a rechazarse como hoy.
