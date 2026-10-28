# Design

## Context

- `ia_cliente.chat_json` corta con "tope diario alcanzado" cuando `llamadas_hoy(proposito) >= tope(proposito)`. Los topes salen de `ia.presupuesto_dia` (clasificador 60, reportero 8, resumen 1). El freno por saldo (`saldo_minimo_usd: 1.0`) es independiente.
- `filtros.Filtros.evaluar`, paso 5: si el título nombra un área de `areas_no_ti`, se anulan los disparadores de dudosa y, si no hay término de TI, se rechaza con `Motivo.NO_TI` sin pasar por la IA. La lista de nivel práctica ya existe en `filtros.nivel.practica` (practicante, aprendiz, pasante, pasantía, trainee, intern, becario, estudiante, sena, etapa productiva…) y está compilada como `self._practica`.
- Las clasificaciones de la IA se guardan en caché por huella (`clasificaciones`), así que una vacante que reaparece no vuelve a gastar llamadas.

## Goals / Non-Goals

**Goals:**
- Que ninguna práctica se rechace sin que la IA lea sus funciones.
- Que los topes no frenen el trabajo normal, manteniendo el corte por saldo.

**Non-Goals:**
- Enviar a la IA vacantes rechazadas por seniority, antigüedad o ubicación.
- Enviar a la IA las vacantes que no son de nivel práctica y nombran un área no TI ("Auxiliar contable" se sigue rechazando por reglas).
- Cambiar de modelo, de proveedor o el tamaño de lote (`max_vacantes_por_llamada: 30`).

## Decisions

**1. Excepción de nivel práctica en el paso 5.** En `evaluar`, antes del rechazo `NO_TI`, si `coincidencias(self._practica, titulo)` la vacante va a dudosa (motivo `DUDOSA`), aunque el título nombre un área no TI. Se usa la lista de nivel práctica que ya existe, sin una lista nueva. El paso 4 (aceptación) no cambia.
- Se descartó una lista blanca de áreas "mixtas" (administrativo + BI, etc.): no escala y es justo el juicio que hace bien la IA.

**2. Topes:** clasificador 300, reportero 20, resumen 3.
- Con 48 corridas al día, 300 cubre hasta ~6 llamadas por corrida, cuando lo habitual son 1–4.
- Se descartó quitar los topes: protegen ante un bucle o un error que repita llamadas. El corte por saldo sigue siendo la protección económica.

**3. Prompt del clasificador.** Se agrega una regla: "Práctica de otra área: acéptala si las funciones principales son de TI (desarrollo, datos/BI, soporte, redes, sistemas de información); si lo de TI es secundario (Excel, digitar en un ERP, 'manejo de sistemas'), recházala." Se mantienen la regla del Aprendiz SENA genérico y la del practicante sin área.

**4. Resumen.** No cambia el código: el tope sigue saliendo de `presupuesto_dia.resumen`. Solo cambia el valor (3) y la redacción del requisito.

## Risks / Trade-offs

- [Más dudosas → más llamadas y latencia por corrida] → Lotes de 30 por llamada (~5–10 s cada una). La corrida sigue muy por debajo de los 28 min de límite.
- [La IA acepta alguna práctica de otra área por error] → El prompt pide que las funciones principales sean de TI. Si aparecen falsos positivos, se ajusta el prompt sin tocar código.
- [Las métricas cambian: baja `no_ti` y suben dudosas y rechazos de la IA] → Es esperado. El resumen diario lo reflejará y no indica una falla.

## Migration Plan

1. Desplegar con `git pull`. Aplica desde la siguiente corrida, sin migración de datos.
2. Rollback: `git revert` del commit. Los topes también se pueden bajar solo en `config.yaml`.
