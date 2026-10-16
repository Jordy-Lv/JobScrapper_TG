## 1. Fases de la card y configuración

- [x] 1.1 Añadir las fases `cuenta` y `cancelada` a `tarjeta_postulacion.py` (texto con barra y segundos, botones «Cancelar» y «Postular», aviso de interrupción) y verificar con pruebas puras en `tests/asistente/test_tarjeta_postulacion.py`
- [x] 1.2 Añadir `asistente.cuenta_regresiva_segundos` a la configuración (5 por defecto, 0 desactiva) y verificar que se valida y se lee en el modelo de config

## 2. Cuenta en la conversación

- [x] 2.1 En `procesar_toque`, arrancar la cuenta (tarea en segundo plano, una edición por segundo, estado en `kv`) y encolar con `n.tocar` solo al terminar; verificar con una prueba de que la cola está vacía durante la cuenta y tiene la postulación después
- [x] 2.2 Adoptar el mensaje de la cuenta como card del `pid` real, incluido el caso `en_tarjeta` del alta, y verificar que no se envían mensajes nuevos
- [x] 2.3 Manejar «Cancelar» y «Postular» (callbacks nuevos en `al_boton`), el doble toque y el «Cancelar» tardío; verificar con una prueba por cada escenario de la spec
- [x] 2.4 Respuesta inmediata del toque del canal con el aviso de los 5 s, sin esperar la cuenta; verificar en `al_toque_canal`
- [x] 2.5 Barrido de arranque que descarta cuentas pendientes y deja la card interrumpida; verificar con una prueba que simula el reinicio

## 3. Pruebas existentes y cierre

- [x] 3.1 Ajustar las pruebas de `test_bot.py` que esperan «En cola» tras el toque (cuenta en 0 en el fixture común) y verificar que toda la suite de `tests/asistente` pasa
- [x] 3.2 Actualizar `docs/asistente/guia-usuario.md` con la cuenta y el botón «Cancelar», y verificar que el texto coincide con la card
- [ ] 3.3 👤 Prueba real del dueño en el bot: tocar ⚡, cancelar a mitad, dejar terminar y tocar dos veces; confirmar que Telegram no limita las ediciones
