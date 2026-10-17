## 1. Barra de progreso (progreso.py)

- [x] 1.1 Agregar `barra(porcentaje, ancho)` con bloques de octavos y pruebas de bordes (0 %, 99 %, 100 %, fracciones)
- [x] 1.2 Agregar el cálculo de avance (etapa + fracción por `cuadro` × intervalo, tope 99 %) y del tiempo restante «~N s» (mínimo 1 s) con pruebas de monotonía y de etapa lenta
- [x] 1.3 Hacer que `etapas`/`texto` de `progreso.py` incluyan la línea de barra, porcentaje y tiempo, y actualizar `test_progreso.py`

## 2. Card de progreso (tarjeta_postulacion.py y conversacion.py)

- [x] 2.1 Pintar la barra y el tiempo en `_cuerpo` para la fase `progreso`, pasando el intervalo de animación desde `Datos`/`conversacion`; actualizar `test_tarjeta_postulacion.py`
- [x] 2.2 Llevar en la conversación el reloj de entrada a cada etapa (`segundos_etapa`) y verificar que el porcentaje no baja entre cuadros (prueba en `test_bot.py`)

## 3. Mensaje de confirmación (resumen_postulacion.py)

- [x] 3.1 Agregar `duracion_s` y `folio` a `DatosResumen` y calcularlos en `_datos_resumen` con `tomada_en` / `terminada_en` y el id de la postulación
- [x] 3.2 Rediseñar `resumen_postulacion.tarjeta`: «✅ Postulación enviada», barra al 100 %, portal, hora, duración, folio, encuesta y hoja de vida; omitir lo que falte; la incierta conserva su texto actual
- [x] 3.3 Actualizar `test_resumen_postulacion.py` y `test_tarjeta_postulacion.py` con el nuevo texto y los casos sin duración ni folio

## 4. Confeti (bot.py y conversacion.py)

- [x] 4.1 Verificar en la versión instalada de `python-telegram-bot` que `send_message` acepta `message_effect_id`; agregar `EFECTO_CONFETI` en `textos.py`
- [x] 4.2 Agregar `efecto` opcional a `Salida.enviar` y a `SalidaTelegram.enviar`, con reintento sin efecto si Telegram responde `BadRequest`; prueba con un bot falso que rechaza el efecto
- [x] 4.3 Actualizar `SalidaFalsa` de las pruebas para registrar el efecto recibido
- [x] 4.4 En `_enviar_resumen`, para `CONFIRMADA`: enviar la card nueva con el efecto, actualizar `mensaje_id` y `_anclar`, y borrar el mensaje de progreso anterior ignorando errores; la incierta sigue editando en el lugar
- [x] 4.5 Pruebas en `test_bot.py`: confirmada envía una card con efecto y borra la anterior; incierta no lleva efecto; las vistas y el seguimiento posteriores editan sin efecto; borrado fallido no rompe

## 5. Cierre

- [x] 5.1 Correr la batería completa (`pytest`) y `ruff`, y dejar todo en verde. Resultado: `ruff` limpio y 1223 pruebas pasan; fallan 7 ajenas al change (no tocan `progreso`, la card, el resumen ni la salida): 4 de `test_extension.py` (elempleo / barra midiendo, del trabajo de extensión que otra sesión tiene sin commitear) y 3 de `tests/radar` (`test_notificador` ×2 por `WinError 193` al ejecutar el script `hermes` en Windows, y `test_punto_entrada_de_la_raiz_muestra_la_ayuda`)
- [ ] 5.2 👤 Prueba del dueño en Telegram real: ver la barra avanzar en una postulación y confirmar que el confeti aparece al enviar (y ajustar el id del efecto si Telegram lo rechaza)
- [ ] 5.3 Archivar el change con `/opsx:archive` para que la spec principal quede actualizada
