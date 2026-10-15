## 1. Selectores de Magneto (corrige la extensión publicada)

- [x] 1.1 🟢 En `assets/asistente/selectores/magneto.json`:
  - en `sesion`: `iniciada` con `[class*='logoutBlock_avatar']` e `img[alt='User Avatar']`, `marca_obligatoria: true` y `espera_ms: 10000`, y quitar de `sin_sesion` el enlace a `web.magneto365.com/sign-in`;
  - en `cuenta.correo`: agregar primero `[class*='mg_account_select'] [class*='tooltip'] strong`;
  - actualizar `version`, `notas` y `verificado.cuenta: true`.

  Verificar con `tests/comun/test_rutas_recursos.py` y las pruebas de selectores en verde.
- [x] 1.2 🟢 Crear `tests/fixtures/extension/mg_con_sesion.html` con el marcado real recortado y sin datos personales. Lleva el enlace «Iniciar sesión» a `web.magneto365.com/sign-in` en el HTML y un script que, a los ~2 s, lo cambia por el bloque `logoutBlock_avatar` con `img[alt='User Avatar']` y el tooltip `mg_account_select` con un correo de prueba. Verificar abriéndolo en un navegador: el enlace cambia por el avatar.
- [ ] 1.3 🟢 En `assets/asistente/selectores/magneto.json`:
  - `sesion.url` y la primera de `cuenta.urls` pasan a `https://www.magneto365.com/co/trabajos/buscar`;
  - agregar `cuenta.abrir: ["[class*='mg_mega_menu_main_header'] img[alt='User Avatar']"]`;
  - actualizar `version` y `notas`.

  En `tests/fixtures/extension/mg_con_sesion.html`, el avatar va dentro de `mg_mega_menu_main_header` y el tooltip con el correo aparece solo al hacer clic en él. Verificar en el Chrome del dueño que `/co/trabajos/buscar` con sesión no tiene el enlace de `sin_sesion`, y las pruebas de selectores en verde.

## 2. Motor de la extensión

- [ ] 2.1 🟡 En `extension/motor.js`:
  - en `sinSesion`: la URL de ingreso manda; si no, la marca presente (con `ocultos`) da sesión; con `marca_obligatoria`, la falta de marca da sin sesión; si no, decide el enlace de ingreso como hoy;
  - agregar `esperarSesion(sel)`, que espera la marca hasta `sesion.espera_ms` (por defecto 5000) y sale de inmediato si ya hay marca, si la URL es de ingreso o si el portal no declara marca;
  - usarla en `revisar` y en `paso`.

  Verificar con las pruebas de Computrabajo de `tests/asistente/test_extension.py` en verde, sin cambios.
- [ ] 2.2 🟢 Subir `extension/manifest.json` a 1.1.0. Verificar con `test_manifiesto_con_permisos_minimos` en verde.
- [ ] 2.3 🟡 En `extension/motor.js`, agregar `abrirCuenta(sel)` (decisión 4) y usarla en `revisar` antes de leer el correo. En `extension/servicio.js`, llamarla en `revisarPortal` antes de `buscarCorreo` en cada página. Verificar con las pruebas de Computrabajo en verde, sin cambios.
- [ ] 2.4 🟢 En `extension/servicio.js` (decisión 5), `vigilarInicioSesion` revisa el token antes de abrir la pestaña y captura los errores, y `latido()` captura los de `latidoUnico`. Verificar con la prueba 3.4.

## 3. Pruebas de la extensión

- [ ] 3.1 🟡 En `tests/asistente/test_extension.py`, agregar:
  - `test_magneto_con_sesion_se_detecta_aunque_el_html_traiga_iniciar_sesion` (latido con `mg_con_sesion.html`: estado `listo` y el correo de prueba);
  - `test_magneto_sin_avatar_queda_sin_sesion` (página sin el avatar, también con el `sin_sesion` antiguo).

  Ajustar `portales_listos()` si hace falta. Verificar ambas pruebas en verde con `.venv/Scripts/python -m pytest tests/asistente/test_extension.py`.
- [ ] 3.2 🟡 Prueba de la vigilancia: después de tocar «Iniciar sesión», la pestaña pasa por una página vacía de `web.magneto365.com/profile/resume` y luego a la página con avatar. La pestaña no se cierra en la página vacía y el portal termina `listo`. Verificar la prueba en verde.
- [ ] 3.3 🟡 `test_magneto_lee_el_correo_tras_abrir_el_menu_del_avatar`: con `mg_con_sesion.html`, el latido informa `listo` y el correo de prueba, que solo aparece tras el clic. Verificar en verde.
- [ ] 3.4 🟡 `test_vigilar_sin_token_no_deja_errores_sin_capturar`: sin token, el mensaje `iniciarSesion` no abre pestaña ni deja rechazos sin capturar en el service worker. Verificar en verde.

## 4. Bot: conexión limitada al portal de la vacante

- [ ] 4.1 🟡 En `buscador_vacantes/asistente/tarjeta.py`, `lineas` y `botones` aceptan `solo=` y `excepto=`. Con `solo=p` sin cuenta de `p`, la línea pendiente de `p`. Verificar con pruebas nuevas en `tests/asistente/test_tarjeta.py`: solo, excepto y sin filtro igual que hoy.
- [ ] 4.2 🟡 En `buscador_vacantes/asistente/conversacion.py`:
  - `_datos_card` pasa `solo=d.plataforma`;
  - `_actualizar_tarjeta` recibe la plataforma (avisos `cuenta_por_confirmar`, `cuenta_distinta`, `portal_listo`, `portal_incompleto` y botones «cuenta») y, si hay card de otra plataforma, pinta o edita el mensaje aparte (kv `tarjeta_otros:{usuario}`);
  - se borra ese kv donde hoy se suelta la tarjeta.

  Verificar con pruebas nuevas en `tests/asistente/test_bot.py`, una por cada escenario del delta `tarjeta-postulacion-asistente`, y las pruebas existentes de la tarjeta en verde.

## 5. Cierre

- [ ] 5.1 🟢 Correr `.venv/Scripts/ruff check .` y la suite completa en segundo plano (`.venv/Scripts/python -m pytest`, ~11 min). Verificar que todo queda en verde.
- [ ] 5.2 👤 Desplegar en el Fedora (`git pull --ff-only` en `~/buscador-vacantes` y reiniciar `buscador-asistente`). Recargar la extensión en el navegador del dueño y tocar ↻ en el popup. Verificar que Magneto pasa a «Confírmala» con el correo correcto, que la página de errores de la extensión no muestra el 401 «navegador sin vincular» y que, al tocar una vacante de Magneto, la card muestra solo la línea de Magneto.
