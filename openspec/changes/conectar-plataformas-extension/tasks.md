## 1. Preparación y decisiones previas

- [x] 1.1 🟢 Revisar y resumir los términos de uso de elempleo y GetOnBoard sobre automatización y uso asistido, y registrar en `docs/asistente/portales.md` (sección «Términos») la cita breve, la fecha y la conclusión (permitida, dudosa o prohibida). Verificar con el documento creado y mostrado al dueño. Si alguna sale «prohibida», se marca como respaldo y se salta su grupo de tareas.
- [x] 1.2 👤 El dueño confirma, a la vista de 1.1, qué plataformas se intentan. Verificar con su respuesta anotada en `docs/asistente/portales.md`.
  Decisión (2026-10-14): **solo elempleo**. GetOnBoard (3 vacantes en toda la historia) y el SPE (0) quedan en paquete de respaldo; se omiten los grupos 5 y 6.
- [x] 1.3 🟢 Medir el SPE con datos reales: consulta de solo lectura (`ssh fedora`, `data/vacantes.db`) del dominio del enlace de las vacantes de las últimas semanas, agrupado por host y fuente. Verificar con la tabla de resultados guardada en `docs/asistente/portales.md` y la decisión escrita: «cubierto por otras plataformas», «hace falta reconocer buscadordeempleo.gov.co» o «respaldo».
- [x] 1.4 🟢 Confirmar la línea base antes de tocar código: `.venv/Scripts/python -m pytest tests/asistente -q` en verde y `ruff check` limpio. Verificar con la salida de ambos.
  Hecho (2026-10-14): `tests/asistente` pasa (dos pruebas de `test_extension.py` fallaron una vez por tiempos del navegador y pasan al repetirlas). Se arreglaron las 3 líneas largas que ya había (E501) y `ruff check` queda limpio. `ruff format --check` marca `radar/corrida.py:77`, que ya estaba y no es de este change.

## 2. Reconocimiento de los portales

Mismo método que la tarea 3.1 de `asistente-postulacion-telegram`; conviene hacerlo en la misma jornada.

- [ ] 2.1 👤 elempleo: recorrer 3 vacantes reales con la sesión del dueño hasta el formulario **sin enviar**, guardando el HTML de cada paso. Registrar:
  - indicadores de sesión iniciada, de ya postulado y de vacante cerrada;
  - tipos de campos y preguntas, y si se puede adjuntar un archivo;
  - captchas o verificaciones vistos;
  - dónde se muestra el correo de la cuenta;
  - páginas del perfil con sus indicadores de sección incompleta y el enlace de registro;
  - modo del CV (`adjunto`, `perfil_unico` o `perfil_multiple`) y si el empleador ve el CV del momento de postular;
  - páginas que el motor no debe tocar.

  Verificar con la sección de elempleo en `docs/asistente/portales.md` y los HTML guardados.
  Avance (2026-10-15): recorridas 2 vacantes (una con pasos extra de video y nota) y registrados los indicadores en `portales.md`. Falta el correo de la cuenta, una vacante cerrada, una con preguntas del empleador y guardar los HTML de cada paso.
- [x] 2.2 (OMITIDA: GetOnBoard queda en respaldo) 👤 GetOnBoard: lo mismo que 2.1, y además anotar cuántas ofertas se aplican dentro del portal y cuántas redirigen a un sitio externo. Verificar con la sección de GetOnBoard en `docs/asistente/portales.md`.
- [x] 2.3 (OMITIDA: el SPE queda en respaldo) 👤 Solo si 1.3 lo pide: reconocimiento del SPE (`buscadordeempleo.gov.co`) con los mismos puntos. Verificar con su sección en `docs/asistente/portales.md`.
- [ ] 2.4 🟡 Recortar los HTML guardados a fixtures sin datos personales en `tests/fixtures/asistente/<plataforma>/`. Verificar con `grep -ri` del nombre, correo, teléfono y documento del dueño sin coincidencias en esas carpetas.
- [ ] 2.5 👤 Una postulación real controlada por plataforma, con la aprobación expresa del dueño en una vacante que él elija, para capturar la página de confirmación. Verificar con la confirmación guardada como fixture y la postulación visible en el portal.

## 3. Reconocimiento del dominio y textos en el servidor

- [x] 3.1 🟡 Ampliar `PLATAFORMAS` en `buscador_vacantes/asistente/vacantes.py` con `elempleo.com` (GetOnBoard y el SPE quedan fuera por 1.2), actualizar el comentario de `datos.py` y completar `NOMBRES_PLATAFORMA` y los enlaces de inicio de `textos.py`. Verificar con pruebas en `tests/asistente/` de `plataforma_de_url` para cada dominio, subdominios incluidos, y un dominio ajeno (por ejemplo `getonbrd.com`) que sigue devolviendo `None`.
- [x] 3.2 🟡 Agregar en `config.yaml` las plataformas nuevas con `automatica: false` y una prueba de coherencia: una plataforma con `automatica: true` MUST tener nombre, dominio y selectores cargados. Verificar con la prueba que falla al quitar un nombre y pasa con todo completo.
- [x] 3.3 🟢 Verificar que, con los dominios reconocidos y `automatica: false`, el toque va al paquete de respaldo con `plataforma_no_automatica` y no hay tarea en la cola. Verificar con una prueba de `nucleo.tocar` para cada plataforma nueva.
- [x] 3.4 🟡 Comprobar el caso del SPE: una vacante con fuente `spe` y enlace de Magneto o elempleo toma la plataforma del enlace, y una con enlace de bolsa externa va a `plataforma_no_soportada`. Verificar con pruebas de `vacantes.resolver` y `camino_automatico`.

## 4. elempleo

Se omite el grupo completo si 1.1 o 1.2 lo descartan.

- [ ] 4.1 🔴 Escribir `assets/asistente/selectores/elempleo.json` (sesión, cuenta, perfil, CV, captcha, textos y pasos de postular) a partir de 2.1 y 2.5, con `verificado` honesto por sección. Verificar con `tests/asistente/test_extension.py` sobre los fixtures de 2.4:
  - postulación completa llega a `enviada`;
  - detecta `ya_postulada`, `vacante_cerrada` y `sin_sesion`;
  - un selector ausente reporta `formulario_desconocido`;
  - el HTML reportado no contiene los valores escritos.
- [ ] 4.2 🟡 Solo si los datos no alcanzan: `extension/adaptadores/elempleo.js` y su entrada en `ADAPTADORES` de `portales.js`. Verificar con la prueba `navegador` del comportamiento concreto que lo exigió. Si no hace falta, dejar anotado en `design.md` que no se creó adaptador.
- [ ] 4.3 🟡 Lectura del correo de la cuenta y detección `sin_sesion`, `incompleto` y `listo`, con la cuenta asociada. Verificar con pruebas `navegador`: la primera detección pide confirmar, una sesión con otro correo no postula y avisa enmascarado, y sin correo legible da `formulario_desconocido`.
- [ ] 4.4 🟡 Pasos `cv_subir` y `cv_verificar` según el modo real del CV de elempleo. Verificar con fixtures del modo detectado en 2.1: sin autorización no se toca el CV, y si la verificación falla se postula con el existente y se registra.
- [ ] 4.4b 🔴 Pasos extra de elempleo (decisión 7): leer y resolver el aviso de datos, el video opcional (omitir), la nota de presentación y las preguntas del empleador, reutilizando las preguntas pendientes de la card. Verificar con fixtures de cada paso: el video se omite, la nota y las preguntas piden respuesta por la card antes de enviar y un paso obligatorio desconocido da `formulario_desconocido`.
- [ ] 4.5 👤 Piloto del dueño: cargar los selectores en el Fedora, activar el permiso en el popup y tocar ⚡ en 3 vacantes reales de elempleo. Verificar con las 3 en `enviada`, visibles en el portal, con el CV enviado correcto y sin datos inventados.

## 5. GetOnBoard

Omitido por decisión del dueño el 2026-10-14 (tarea 1.2): GetOnBoard queda en paquete de respaldo; se retoma solo si el volumen crece.

- [x] (OMITIDA) 5.1 🔴 Escribir `assets/asistente/selectores/getonboard.json` a partir de 2.2, con el manejo de la aplicación externa (salida de los dominios permitidos → `formulario_desconocido` o respaldo, sin llenar nada). Verificar con `tests/asistente/test_extension.py` sobre sus fixtures: postulación completa en el portal, ya postulado, cerrada, sin sesión y oferta con aplicación externa.
- [x] (OMITIDA) 5.2 🟡 Adaptador solo si los datos no alcanzan (igual que 4.2). Verificar igual que 4.2.
- [x] (OMITIDA) 5.3 🟡 Correo de la cuenta, estados de sesión y perfil, y modo del CV, como en 4.3 y 4.4. Verificar con las mismas pruebas sobre los fixtures de GetOnBoard.
- [x] (OMITIDA) 5.4 👤 Piloto del dueño en 3 vacantes reales de GetOnBoard. Verificar igual que 4.5.

## 6. Servicio Público de Empleo

Omitido por decisión del dueño el 2026-10-14 (tareas 1.2 y 1.3): el SPE tiene 0 vacantes y queda en paquete de respaldo.

- [x] (OMITIDA) 6.1 🔴 Escribir `assets/asistente/selectores/spe.json` a partir de 2.3. Verificar con las mismas pruebas que 4.1 sobre sus fixtures.
- [x] (OMITIDA) 6.2 🟡 Estados de sesión, cuenta y perfil del SPE. Verificar como 4.3.
- [x] (OMITIDA) 6.3 👤 Piloto del dueño en 3 plazas reales del SPE. Verificar igual que 4.5.

## 7. Habilitación, invitados y documentación

- [ ] 7.1 👤 Por cada plataforma con el piloto exitoso, poner `automatica: true` en `config.yaml`, desplegar en el Fedora (`git pull --ff-only` y reinicio del servicio) y verificar que un toque de ⚡ termina en `enviada`. Las que no pasen el piloto quedan en `false`, con el motivo anotado en `docs/asistente/portales.md`.
- [ ] 7.2 👤 Probar con 2 o 3 invitados durante al menos 3 días. Verificar que el log no tiene errores sin resolver y recoger sus comentarios; las preguntas nuevas se agregan al banco.
- [ ] 7.3 🟢 Actualizar `docs/asistente/guia-usuario.md` (plataformas con postulación automática y las que siguen con paquete), la política de datos si nombra a los portales, `docs/asistente/tienda-edge` (qué dominios se piden y para qué) y el `README.md`. Verificar con una lectura de los textos y `grep` de las listas viejas de plataformas sin resultados.
- [ ] 7.4 🟡 Ejecutar la suite completa y `ruff check` / `ruff format --check`. La suite tarda unos 11 minutos: lanzarla en segundo plano y no tocar archivos mientras corre. Verificar con todo en verde (la prueba intermitente de `test_extension.py` por tiempos es la única excepción conocida).
- [ ] 7.5 🟢 Archivar este change después de `asistente-postulacion-telegram`, porque sus deltas usan `ADDED` y complementan specs que solo existen al archivar ese change. Verificar con `openspec validate` y `openspec list --specs`.
