# Fase 0: diagnóstico del silencio del 24/10

| | |
|---|---|
| **Dificultad** | 👤 del dueño (correr las consultas en el Fedora) + 🟢 ligera (anotar el resultado) |
| **Change de OpenSpec** | ninguno: solo se diagnostica y se documenta |
| **Atiende** | punto 1 del diagnóstico |
| **Depende de** | nada. Conviene hacerla antes de las demás fases, porque `intentos` y `corridas` se borran a los 30 días y `descartes` a los 14. |

## Objetivo

Confirmar con datos por qué no se publicó nada en el grupo después de las 8:33 del sábado 24 de octubre, y decidir si hace falta un arreglo urgente antes de la fase 1. Las hipótesis están en [estado-actual.md §6](estado-actual.md#6-hipótesis-del-silencio-del-2410-después-de-las-833).

## Pasos (en el Fedora, dentro de `~/buscador-vacantes`)

> **La base guarda las horas en UTC.** Las 8:33 de Bogotá son las `13:33Z`, y el día 24 de Bogotá empieza a las `2026-10-24T05:00Z`.

### 1. ¿Hubo corridas?

```bash
systemctl --user list-timers 'buscador*'
journalctl --user -u buscador --since "2026-10-24 08:00" --no-pager | tail -n 200
grep "Corrida " logs/2026-10-24.log
```

Debe haber una línea `Corrida N (...)` cada 30 minutos con los conteos por etapa. Si faltan corridas, la causa es la hipótesis 6: el equipo suspendido, la red caída o `uv` fallando.

### 2. Conteos de cada corrida

Primero, para confirmar el formato de las fechas:

```bash
sqlite3 -readonly data/vacantes.db "select inicio from corridas order by id desc limit 1;"
```

Después, los conteos de cada corrida del día:

```sql
-- sqlite3 -readonly -header -column data/vacantes.db
select id, inicio, crudas, duplicadas, dudosas, ia_aceptadas, ia_rechazadas,
       pendientes, enviadas, detalles_pedidos, error, descartes_json
from corridas where inicio >= '2026-10-24T05:00' order by id;
```

### 3. Estado de las fuentes y peticiones del día

```sql
select fuente, count(*) as peticiones,
       sum(status between 200 and 299) as ok,
       sum(items) as items,
       group_concat(distinct tipo_error) as errores,
       sum(desafio) as desafios
from intentos where ts >= '2026-10-24T05:00' group by fuente;

select * from fuentes_estado;
select clave, valor from kv where clave like 'ritmo:%' or clave like 'ia_%';
```

### 4. IA, colas y descartes

```sql
select proposito, count(*), sum(ok), group_concat(distinct motivo)
from ia_uso where ts >= '2026-10-24T05:00' group by proposito;

select (select count(*) from pendientes) as pendientes_ia,
       (select count(*) from pendientes_detalle) as pendientes_detalle,
       (select count(*) from por_enviar) as por_enviar;

select etapa, motivo, count(*) as n
from descartes where ultima_vez >= '2026-10-24T05:00'
group by etapa, motivo order by n desc;

select * from incidentes where cerrado_en is null;
```

> Si `descartes` no existe o está vacía, es que el commit `139372f` todavía no está desplegado. Anotarlo, porque la [fase 3](fase-3-recuperacion-y-limpieza.md) depende de esos datos.

### 5. Telegram

```bash
grep -i "telegram rechaz\|429\|retry_after" logs/2026-10-24.log | tail -n 50
```

## Cómo leer el resultado

| Lo que se ve | Causa | Qué hacer |
|---|---|---|
| `crudas` alto, `duplicadas` ≈ `crudas`, `enviadas = 0`, sin errores | 1: fin de semana y saturación | Nada urgente. Lo atienden la fase 1 (más términos de aprendizaje) y la fase 5b (frescura). |
| `fuentes_estado.cooldown_hasta` futuro, `bloqueo` o `captcha` en `intentos` | 2: cooldown en cadena | Adelantar de la [fase 4](fase-4-observabilidad.md) el incidente desde el primer bloqueo, y de la [fase 5a](fase-5-recoleccion-robusta.md) la huella y el ritmo. |
| `pendientes_detalle` alto, `detalles_pedidos = 0` | 3: detalle de LinkedIn | Adelantar el detalle desacoplado de la fase 5b. |
| `por_enviar` > 0 y «Telegram rechazó» en el log | 4: Telegram | **Arreglo urgente**: revisar el bot y el grupo, y adelantar «el healthcheck falla si Telegram rechaza» (fase 4). |
| `ia_uso` con `ok = 0` o saldo menor de 1 | 5: DeepSeek | **Arreglo urgente**: recargar el saldo y adelantar el incidente `ia:clasificador` (fase 1, bloque 4). |
| Sin corridas después de `13:33Z` | 6: el servicio no corrió | Revisar el timer, el equipo y la red; adelantar la alerta de sequía (fase 4). |

## Entregable

Anotar al final de este documento, en una sección «Resultado»:

- la hipótesis confirmada (puede ser más de una);
- las cifras que la sostienen (corridas, crudas, duplicadas, enviadas, estado de las fuentes);
- si hace falta un arreglo urgente, y cuál;
- si `descartes` tenía datos, desde qué fecha.

## Criterios de aceptación

- [ ] Las consultas de los pasos 1 a 5 se corrieron y su salida resumida está en este documento.
- [ ] La causa del silencio quedó identificada con datos, o descartadas todas las hipótesis con datos.
- [ ] Hay una decisión escrita: seguir con la fase 1, o adelantar un arreglo urgente.

## Sesión recomendada

**Seguir aquí** o en una sesión corta: el dueño pega las salidas y Claude las interpreta. La fase 1 va en **sesión nueva**.

## Resultado

*(pendiente: lo llena el dueño con la salida de los pasos 1 a 5)*
