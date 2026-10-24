## 1. Textos y tarjeta

- [x] 1.1 🟢 `textos.py`: el paso 5 queda solo en vincular el navegador, se agrega el texto del paso 6 y el resto del alta pasa a «de 6». Verificar con una prueba que `NAVEGADOR` ya no pide iniciar sesión y `PLATAFORMAS` sí.
- [x] 1.2 🟡 `tarjeta.py`: soportar el paso, con las plataformas automáticas sembradas como pendientes, la esperada resaltada y las demás como opcionales, más el botón «Omitir por ahora». Verificar con pruebas de `lineas` y `botones` en `tests/asistente/test_tarjeta.py`.

## 2. Flujo del alta

- [x] 2.1 🟡 `conversacion.py`: `navegador_vinculado` lleva al paso `plataformas` en lugar de llamar a `_terminar_alta`; `_continuar_alta` pinta el paso. Verificar con una prueba en `tests/asistente/test_bot.py`: al vincular no se envía el cierre ni arranca la vacante pendiente.
- [x] 2.2 🟡 Cumplimiento del paso: evaluarlo tras `portal_listo`, `portal_incompleto` y el botón `cuenta:<p>:si`. Con vacante pendiente solo cuenta su plataforma; sin vacante, cualquiera. Verificar con pruebas de la plataforma esperada confirmada (arranca), otra plataforma confirmada (sigue abierto) y sin vacante (cierra con el mensaje al grupo).
- [x] 2.3 🟡 Salto del paso: al entrar, saltar si la cuenta esperada ya está confirmada con sesión abierta en el último latido, o si la plataforma de la vacante no es automática. Verificar con pruebas de reinstalación y de plataforma no automática.
- [x] 2.4 🟢 Botón «Omitir por ahora»: cierra el alta y encola la vacante pendiente como hoy. Verificar con pruebas con y sin vacante pendiente.
- [x] 2.5 🟡 Retomar con `/start` durante el paso: tarjeta nueva al final, aviso de vacante guardada y borrado tolerante de la anterior. Verificar con una prueba de `/start v_<id>` con el paso abierto.

## 3. Verificación

- [x] 3.1 🟡 Suite completa y `ruff check` / `ruff format --check`. Verificar que solo fallan las 3 pruebas propias de Windows que ya fallaban.
- [x] 3.2 🟢 Actualizar `docs/asistente/guia-usuario.md` con el paso 6. Verificar leyendo la sección del alta.

## 4. Despliegue y prueba real

- [x] 4.1 👤 Desplegar en el Fedora (`git pull --ff-only` y reinicio de `buscador-asistente`). Verificar con el servicio activo y sin errores en el log.
- [ ] 4.2 👤 Prueba real con una cuenta de Telegram nueva: tocar ⚡ en una vacante, registrarse, vincular el navegador, comprobar que la postulación no arranca hasta confirmar la cuenta del portal, y repetir con «Omitir por ahora». Verificar con la postulación en `enviada` en el primer caso y en cola esperando sesión en el segundo.
- [ ] 4.3 🟢 Archivar el change tras el despliegue. Verificar con `openspec validate` y `openspec list --specs`.
