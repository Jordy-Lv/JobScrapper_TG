# Proposal

## Why

La IA (DeepSeek) solo ve las vacantes dudosas, y unos topes diarios conservadores limitan su uso:
- El 2026-10-04 el clasificador usó 23 de 60 llamadas.
- El resumen diario salió sin recomendaciones porque una prueba de madrugada gastó su única llamada del día.
- Las reglas rechazan sin consultar a nadie las prácticas cuyo título nombra un área no TI ("Practicante administrativo", "Aprendiz de logística"). Así se pueden perder prácticas cuyas funciones sí son de TI (datos/BI, soporte, sistemas), justo en la categoría prioritaria del canal.

El usuario pidió apoyarse más en la IA.

## What Changes

- **Topes diarios más altos:** clasificador de 60 a 300 llamadas, reportero de 8 a 20 y resumen de 1 a 3. Se mantiene el corte por saldo bajo (1 USD), así que la cuenta no se puede vaciar.
- **Prácticas a la IA en lugar de rechazo directo:** una vacante con un término de nivel práctica en el título (practicante, aprendiz, pasante, pasantía, trainee, intern, becario, estudiante en práctica…) que las reglas iban a rechazar por "no es TI" queda dudosa y la decide la IA. Los rechazos por seniority, antigüedad y ubicación no cambian.
- **Prompt del clasificador:** una práctica de otra área se acepta si sus funciones principales son de TI. Si lo de TI es secundario (Excel, "manejo de sistemas", digitar en un ERP), se rechaza.
- **Resumen diario:** sigue siendo un solo resumen al día con una llamada de IA. El tope de 3 deja margen para reintentos y pruebas sin dejar al resumen real sin recomendaciones.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `filtrado-vacantes`: el requisito "Veredicto aceptar, rechazar o dudosa" cambia el paso 5 para las vacantes de nivel práctica, y su escenario "Fuera de TI".
- `incidentes-reportero`: en el requisito "Presupuesto de IA y medición de consumo", el tope por defecto del reportero pasa de 8 a 20.
- `resumen-diario`: el requisito "Una sola llamada y datos sanitizados" pasa a "una llamada por resumen", con un tope diario configurable para reintentos.

## Impact

- `buscador_vacantes/filtros.py`, paso 5 de `evaluar`.
- `config.yaml`: `ia.presupuesto_dia` y `clasificador.prompt_sistema`.
- Pruebas en `tests/test_filtros.py` y `tests/test_config.py`, y la sección de filtrado del `README.md`.
- Más dudosas por corrida (el dry-run del SPE ya produjo 46 rechazos `no_ti`). Se estiman 2–4 llamadas del clasificador por corrida al principio, que bajan a medida que la caché por huella se llena.
- Costo: unos 4 mil tokens por llamada. Incluso con las 300 llamadas al día serían ~1,2 M tokens de entrada, del orden de centavos de dólar al día con la tarifa de DeepSeek.
