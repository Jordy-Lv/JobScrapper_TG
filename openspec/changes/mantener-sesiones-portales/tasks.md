## 1. Permiso y diagnóstico (solo lectura de metadatos)

- [x] 1.1 Declarar `cookies` en `optional_permissions` del manifiesto y actualizar `test_manifiesto_con_permisos_minimos` para exigir que NO esté en `permissions`; verificar con `pytest tests/asistente/test_extension.py -k manifiesto`
- [x] 1.2 Crear `extension/sesion.js` con `diagnosticarSesion(plataforma)`: lee con `chrome.cookies.getAll` las cookies del portal y devuelve solo nombre, `session`, vencimiento y `httpOnly` (nunca `value`); verificar con una prueba unitaria que el resultado no contiene el valor
- [x] 1.3 Clasificar la sesión («se pierde al cerrar el navegador», «dura hasta <fecha>», «sin datos») a partir de las cookies nombradas en `sesion.cookies` del selector, con la lista completa disponible para el diagnóstico; verificar con pruebas de las tres clasificaciones
- [x] 1.4 Guardar la clasificación en `chrome.storage.local` junto al estado del portal y mostrarla en la configuración del portal del popup («Dura hasta …»); verificar con la prueba del popup y a mano en Chrome
- [ ] 1.5 👤 Con el permiso concedido en el Chrome del dueño, anotar para elempleo, Magneto y Computrabajo si la cookie de autenticación es de sesión o persistente y cuándo vence, y llenar `sesion.cookies` en `assets/asistente/selectores/*.json`; verificar con el resultado anotado en `docs/asistente/portales.md`

## 2. Aviso de sesión perdida (servidor)

- [ ] 2.1 En `latido` de `api.py`, avisar con `portal_sin_sesion` solo al pasar de `listo`/`incompleto` a `sin_sesion` (usando `aviso`), sin repetir mientras siga cerrada ni avisar a un portal que nunca tuvo sesión; verificar con pruebas en `tests/asistente/test_api.py` de los cuatro escenarios del spec
- [ ] 2.2 Agregar los textos del aviso por motivo (`cookie_de_sesion`, `vencida`, `borrada_al_cerrar`, `cerrada_por_el_portal`, sin motivo) en `textos.py` y su manejo en `conversacion.py`; verificar con pruebas de texto por motivo
- [ ] 2.3 Si hay una postulación en `esperando_sesion` para ese portal, poner el aviso en su tarjeta de espera y no enviar mensaje aparte (`espera.py`); verificar con una prueba de `tests/asistente/test_espera.py`

## 3. Persistir la sesión (opt-in por portal)

- [ ] 3.1 Agregar el ajuste `mantener_sesion` por portal en `chrome.storage.local` y el interruptor «Mantener la sesión» en la configuración del portal, desactivado por defecto, que pide el permiso `cookies` al activarse y se queda apagado si se rechaza; verificar con pruebas del popup
- [ ] 3.2 Implementar en `sesion.js` `persistirCookies(plataforma)` con `chrome.cookies.get`/`set` sobre las cookies de `sesion.cookies` que sean de sesión, conservando valor y atributos y poniendo `expirationDate` con `sesion.persistir_dias` (30 por defecto); verificar con pruebas de que solo cambia el vencimiento y que no toca cookies no nombradas ni portales con la opción apagada
- [ ] 3.3 Registrar `chrome.cookies.onChanged` a nivel superior de `servicio.js` para volver a persistir una cookie nombrada que el portal reemite como de sesión, sin bucle; verificar con una prueba de que la reescritura no dispara otra
- [ ] 3.4 Si `chrome.cookies.set` falla, mostrar «No pude mantener la sesión» en la tarjeta del portal y registrar el error sin el valor; verificar con una prueba que simula el fallo
- [ ] 3.5 Revocar el permiso con la opción activa: dejar de reescribir y mostrar que falta el permiso; verificar con una prueba de `permissions.onRemoved`

## 4. Mantener viva la sesión y motivo de la pérdida

- [ ] 4.1 Con la opción activa, usar el intervalo `sesion.mantener_min` del portal en `estadoPortales`, aplazar la visita si hay una postulación en curso y registrar si el vencimiento avanzó tras la visita; verificar con pruebas de intervalo, aplazamiento y registro
- [ ] 4.2 Calcular el motivo al pasar a `sin_sesion` (`cookie_de_sesion`, `vencida`, `borrada_al_cerrar`, `cerrada_por_el_portal`) con la marca de «persistida» por portal, y enviarlo en el campo `motivo` del latido; verificar con una prueba por cada motivo y que sin el permiso se informe el motivo de hoy
- [ ] 4.3 Pruebas en el navegador de pruebas de la suite (`test_extension.py`): sesión persistida que sobrevive al reinicio simulado y portal que cierra la sesión con las cookies presentes; verificar con `pytest tests/asistente/test_extension.py`

## 5. Documentación, tienda y despliegue

- [ ] 5.1 Documentar en `docs/asistente/portales.md` el diagnóstico, el interruptor, los motivos de pérdida y cómo permitir las cookies de un portal en Chrome; verificar leyendo la sección
- [ ] 5.2 Justificar el permiso `cookies` en `docs/asistente/tienda-edge/ficha.md` (solo metadatos, opt-in, sin valores) y subir la versión de la extensión en el manifiesto; verificar con la prueba de versión
- [ ] 5.3 Suite completa en verde (`.venv/Scripts/python -m pytest` en segundo plano) y `.venv/Scripts/ruff check`; verificar con ambas salidas
- [ ] 5.4 👤 Desplegar en el Fedora (`git pull --ff-only` y reiniciar el servicio) y recargar la extensión en el Chrome del dueño; activar «Mantener la sesión» en elempleo y Magneto y comprobar al día siguiente que las sesiones siguen iniciadas
