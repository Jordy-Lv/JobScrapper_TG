## 1. Selectores de Magneto (corrige la extensión publicada)

- [x] 1.1 🟢 En `assets/asistente/selectores/magneto.json`:
  - en `sesion`: `iniciada` con `[class*='logoutBlock_avatar']` e `img[alt='User Avatar']`, `marca_obligatoria: true` y `espera_ms: 10000`, y quitar de `sin_sesion` el enlace a `web.magneto365.com/sign-in`;
  - en `cuenta.correo`: agregar primero `[class*='mg_account_select'] [class*='tooltip'] strong`;
  - actualizar `version`, `notas` y `verificado.cuenta: true`.

  Verificar con `tests/comun/test_rutas_recursos.py` y las pruebas de selectores en verde.
- [x] 1.2 🟢 Crear `tests/fixtures/extension/mg_con_sesion.html` con el marcado real recortado y sin datos personales. Lleva el enlace «Iniciar sesión» a `web.magneto365.com/sign-in` en el HTML y un script que, a los ~2 s, lo cambia por el bloque `logoutBlock_avatar` con `img[alt='User Avatar']` y el tooltip `mg_account_select` con un correo de prueba. Verificar abriéndolo en un navegador: el enlace cambia por el avatar.

## 2. Motor de la extensión

- [ ] 2.1 🟡 En `extension/motor.js`:
  - en `sinSesion`: la URL de ingreso manda; si no, la marca presente (con `ocultos`) da sesión; con `marca_obligatoria`, la falta de marca da sin sesión; si no, decide el enlace de ingreso como hoy;
  - agregar `esperarSesion(sel)`, que espera la marca hasta `sesion.espera_ms` (por defecto 5000) y sale de inmediato si ya hay marca, si la URL es de ingreso o si el portal no declara marca;
  - usarla en `revisar` y en `paso`.

  Verificar con las pruebas de Computrabajo de `tests/asistente/test_extension.py` en verde, sin cambios.
- [ ] 2.2 🟢 Subir `extension/manifest.json` a 1.1.0. Verificar con `test_manifiesto_con_permisos_minimos` en verde.

## 3. Pruebas de la extensión

- [ ] 3.1 🟡 En `tests/asistente/test_extension.py`, agregar:
  - `test_magneto_con_sesion_se_detecta_aunque_el_html_traiga_iniciar_sesion` (latido con `mg_con_sesion.html`: estado `listo` y el correo de prueba);
  - `test_magneto_sin_avatar_queda_sin_sesion` (página sin el avatar, también con el `sin_sesion` antiguo).

  Ajustar `portales_listos()` si hace falta. Verificar ambas pruebas en verde con `.venv/Scripts/python -m pytest tests/asistente/test_extension.py`.
- [ ] 3.2 🟡 Prueba de la vigilancia: después de tocar «Iniciar sesión», la pestaña pasa por una página vacía de `web.magneto365.com/profile/resume` y luego a la página con avatar. La pestaña no se cierra en la página vacía y el portal termina `listo`. Verificar la prueba en verde.

## 4. Bot: conexión limitada al portal de la vacante

- [ ] 4.1 🟡 En `buscador_vacantes/asistente/tarjeta.py`, `lineas` y `botones` aceptan `solo=` y `excepto=`. Con `solo=p` sin cuenta de `p`, la línea pendiente de `p`. Verificar con pruebas nuevas en `tests/asistente/test_tarjeta.py`: solo, excepto y sin filtro igual que hoy.
- [ ] 4.2 🟡 En `buscador_vacantes/asistente/conversacion.py`:
  - `_datos_card` pasa `solo=d.plataforma`;
  - `_actualizar_tarjeta` recibe la plataforma (avisos `cuenta_por_confirmar`, `cuenta_distinta`, `portal_listo`, `portal_incompleto` y botones «cuenta») y, si hay card de otra plataforma, pinta o edita el mensaje aparte (kv `tarjeta_otros:{usuario}`);
  - se borra ese kv donde hoy se suelta la tarjeta.

  Verificar con pruebas nuevas en `tests/asistente/test_bot.py`, una por cada escenario del delta `tarjeta-postulacion-asistente`, y las pruebas existentes de la tarjeta en verde.

## 5. Cierre

- [ ] 5.1 🟢 Correr `.venv/Scripts/ruff check .` y la suite completa en segundo plano (`.venv/Scripts/python -m pytest`, ~11 min). Verificar que todo queda en verde.
- [ ] 5.2 👤 Desplegar en el Fedora (`git pull --ff-only` en `~/buscador-vacantes` y reiniciar `buscador-asistente`). Recargar la extensión en el navegador del dueño y tocar ↻ en el popup. Verificar que Magneto pasa a «Confírmala» con el correo correcto y que, al tocar una vacante de Magneto, la card muestra solo la línea de Magneto.
