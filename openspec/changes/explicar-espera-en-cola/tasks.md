## 1. Estado de los portales en el latido (`api.py`)

- [x] 1.1 🟡 Guardar en `navegadores.portales_json` el estado completo de cada plataforma (`estado`, `motivo`, `cuenta`, `visto`), incluido `sin_sesion` (conservando el `cuenta` previo) y `sin_permiso` para las plataformas con selectores ausentes del latido; nunca el correo. Verificar con pruebas nuevas en `tests/asistente/test_api.py`: Magneto `sin_sesion` + `enlace_ingresar` queda guardado, elempleo ausente queda `sin_permiso`, y los avisos `cuenta_*` / `portal_*` no se repiten (las pruebas existentes siguen verdes).
- [x] 1.2 🟢 Aceptar `pausado: bool | None` en `Latido` y guardarlo en `portales_json` (`_pausado`). Verificar con una prueba de latido con y sin el campo.
- [x] 1.3 🟡 Excluir de `disponibles` las plataformas con `automatica = False` sin cambiar `cuentas` de la respuesta. Verificar con una prueba: con Magneto apagado, el latido no entrega la postulación de Magneto en cola; al encenderlo, el siguiente latido la entrega.
- [x] 1.4 🟢 En `extension/servicio.js`, enviar `pausado` de `ajustes()` en el cuerpo del latido, sin tocar `ejecutar` ni `motor.js`. Verificar con una prueba en `tests/asistente/test_extension.py` que el cuerpo del latido lleva `pausado`.

## 2. Diagnóstico de la espera (`espera.py`, `cola.py`, `nucleo.py`)

- [x] 2.1 🟡 Extraer de `cola.siguiente()` la función `restriccion(usuario_id, plataforma, ahora)` (`en_curso`, `tope_diario` con la hora en que vuelve el cupo, `pausa` con su hora de fin) y hacer que `siguiente()` la use. Verificar con `pytest tests/asistente/test_cola.py` en verde y pruebas nuevas de cada restricción.
- [x] 2.2 🟡 Crear `buscador_vacantes/asistente/espera.py` con `Entrada`, `Causa` y `causa()` según el orden del spec (navegador, latido, versión, pausa, plataforma, permiso, sesión, cuenta, perfil, cola) y la regla de varios navegadores. Verificar con `tests/asistente/test_espera.py` nuevo: un escenario por causa en Computrabajo, Magneto y elempleo, prioridad versión > sesión, dos navegadores (uno listo ⇒ sin causa) y sin causa.
- [x] 2.3 🟢 Agregar `nucleo.espera(pid)` que arma la `Entrada` desde la base y la configuración. Verificar con una prueba en `tests/asistente/test_nucleo.py` que reproduce el caso de la postulación 43 (Magneto sin sesión ⇒ causa `sin_sesion`).

## 3. Card en cola (`tarjeta_postulacion.py`, `textos.py`)

- [x] 3.1 🟢 Agregar a `textos.py` `ESPERAS` (plantilla por causa), `URL_INGRESO` (Computrabajo `/acceso/`, Magneto `web.magneto365.com/sign-in`, elempleo con respaldo en la portada) y el dominio de cada portal para el permiso. Verificar con una prueba que cada causa del diagnóstico tiene texto y que ningún texto contiene motivos internos (`enlace_ingresar`, `fuera_del_portal`).
- [x] 3.2 🟡 Agregar `Card.espera` (con valor por defecto, compatible con cards guardadas) y pintar en `_cuerpo` y `botones` el mensaje y los botones de cada causa: «Iniciar sesión» + «Crear cuenta», «Vincular navegador», «Actualizar extensión» solo con tienda, botones de cuenta (`cuenta:<plataforma>:…`) sin duplicar `botones_conexion`, y sin botones en plataforma apagada y esperas de la cola. Verificar con pruebas en `tests/asistente/test_tarjeta_postulacion.py` para cada escenario del spec de la card y con `Card.de_texto` de una card antigua sin `espera`.

## 4. Actualización automática (`conversacion.py`, `servicio.py`)

- [x] 4.1 🟡 Implementar `_revisar_esperas(usuario)`: recorre las postulaciones `postular` en `en_cola`/`esperando_navegador` con card, calcula la causa y solo si cambió la guarda y repinta con `_pintar_card`. Atender el aviso `esperas` que el latido manda al final. Verificar con pruebas en `tests/asistente/test_bot.py`: sin sesión ⇒ la card muestra el aviso; latidos repetidos ⇒ ninguna edición; sesión iniciada ⇒ vuelve a «En cola. Te aviso el resultado.».
- [x] 4.2 🟢 Llamar a la revisión de esperas en la vigilancia de cada minuto (`servicio.py`) y después de `/plataformas on|off`. Verificar con una prueba de `/plataformas magneto off` que cambia la card a «plataforma apagada» y, con `on`, la devuelve.
- [x] 4.3 🟡 Prueba de punta a punta sin navegador: latido Magneto sin sesión ⇒ card con «Iniciar sesión»; latido con permiso de elempleo faltante y luego concedido sin sesión ⇒ la card pasa de «sin permiso» a «sin sesión» en el mismo mensaje. Verificar con la prueba en verde.

## 5. Cierre local

- [x] 5.1 🔴 Correr la suite completa y `ruff check` / `ruff format --check` en segundo plano (~11 min), sin tocar archivos mientras corre. Verificar con todo en verde (salvo los fallos de radar ya conocidos en Windows). Recomendar sesión nueva antes de empezarla si el contexto ya está cargado.
- [x] 5.2 🟢 Hacer commit solo de los archivos de este change, en español y sin atribuciones a la IA. Verificar con `git show --stat` y `git log -1 --format=%B`.

## 6. Despliegue y prueba real

- [ ] 6.1 👤 Desplegar en el Fedora (`git pull --ff-only` en `~/buscador-vacantes` y reiniciar `buscador-asistente`) y recargar la extensión. Verificar que el servicio arranca y que el siguiente latido reescribe `portales_json` con `estado` y `motivo`.
- [ ] 6.2 👤 Prueba real: con sesión cerrada en Magneto, tocar ⚡ en una vacante de Magneto que no se haya postulado. Verificar que la card dice «inicia sesión en Magneto» con el botón «Iniciar sesión», que al iniciar sesión vuelve sola a «En cola» y luego avanza al progreso.
- [ ] 6.3 👤 Confirmar la URL de ingreso de elempleo con el botón de la card (o en el reconocimiento) y ajustar `URL_INGRESO` si hace falta. Verificar que el botón abre la página de ingreso.
- [ ] 6.4 🟢 Archivar con `/opsx:archive`. Verificar con `openspec validate explicar-espera-en-cola` y `openspec list`.
