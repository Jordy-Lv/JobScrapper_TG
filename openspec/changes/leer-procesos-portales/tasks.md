## 1. Reconocimiento (antes de codificar)

- [ ] 1.1 👤 Con el Chrome del dueño, abrir «Mis procesos» de Computrabajo y «Procesos activos» de Magneto con postulaciones en distintos estados. Anotar los textos de estado que aparecen, dónde está el enlace de cada oferta, si hay paginación y dónde están la bandeja de mensajes y su contador. Verificar dejando las notas en la memoria `reconocimiento-*` y en `docs/asistente/portales.md`.
- [ ] 1.2 🟡 Guardar fixtures HTML anonimizados en `tests/fixtures/extension/` (`ct_mis_procesos.html`, `mg_procesos.html`, una página sin filas y otra redirigida al inicio de sesión). Verificar abriéndolos en el navegador de pruebas y con una prueba corta que lea sus clases.

## 2. Selectores y motor

- [ ] 2.1 🟢 Agregar la sección `procesos` con `verificado: false` a `computrabajo.json` y `magneto.json`, con los selectores, `id_oferta`, `estados` y `mensajes` del reconocimiento, y subir `version`. Verificar con la prueba de carga de selectores y `json.load`.
- [ ] 2.2 🟡 Escribir `leerFilas` en `motor.js` (campos por texto o atributo, `siguiente` hasta `max_paginas`, tope `max_filas`, `mensajes`), sin clics fuera del paso de página. Verificar con pruebas en `test_extension.py` sobre los fixtures de 1.2.
- [ ] 2.3 🟡 En `servicio.js`, atender `procesos` del latido: pestaña en segundo plano, comprobación de portal y sesión, `leerFilas`, `POST /procesos/{plataforma}` y cierre de la pestaña, y abortar si aparece una verificación. Subir la versión de `manifest.json`. Verificar con una prueba de extensión de punta a punta con el servidor de pruebas y con la de `sin_sesion`.

## 3. Servidor

- [ ] 3.1 🟡 Tabla `procesos_portal_foto` (usuario, plataforma, foto JSON, pedida_en, recibida_en, sin_mapear) en la versión de esquema siguiente, y sección `asistente.seguimiento.portales` en `config.yaml` / `comun/config.py`. Verificar con pruebas de `test_datos.py` y de configuración.
- [ ] 3.2 🟡 Programación en `/latido`: pedir lectura solo con las condiciones del requisito «Lectura programada por el servidor». Verificar con pruebas en `test_api.py` para cada escenario (debida, fuera de ventana, postulación en curso, no verificado, reintento).
- [ ] 3.3 🟡 `POST /procesos/{plataforma}` y `procesos_portal.py`: normalizar, comparar con la foto anterior, mapear estados, asociar por `id_oferta` y luego por empresa y cargo, registrar eventos con `Procesos.registrar`, aplicar la regla de la primera foto y ofrecer procesos externos una sola vez. Verificar con pruebas en `tests/asistente/test_procesos_portal.py` para cada escenario del spec.
- [ ] 3.4 🟢 Llenar `procesos.id_oferta` al abrir un proceso desde la URL de la vacante con la expresión del JSON, migrando también los procesos existentes. Verificar con una prueba.
- [ ] 3.5 🟡 Mensajes del portal: aumento del contador → aviso urgente con enlace, asociado a la empresa si se puede. Incidentes por marcado roto → aviso al dueño una vez por día. Verificar con pruebas.

## 4. Documentación y cierre local

- [ ] 4.1 🟢 Documentar en `docs/asistente/portales.md` la lectura de procesos por portal (frecuencia, solo lectura, términos revisados) y en `guia-usuario.md` qué ve el usuario. Verificar leyendo el texto.
- [ ] 4.2 🔴 Suite completa y `ruff` en segundo plano. Verificar con todo en verde. Recomendar sesión nueva antes de empezar si el contexto está cargado.
- [ ] 4.3 🟢 Commit solo de los archivos de este change, en español y sin atribuciones a la IA. Verificar con `git show --stat` y `git log -1 --format=%B`.

## 5. Despliegue y piloto

- [ ] 5.1 👤 Desplegar el servidor en el Fedora y recargar la extensión. Con `verificado: false` no debe pedirse ninguna lectura. Verificar en el log del latido.
- [ ] 5.2 👤 Piloto en Computrabajo: poner `procesos.verificado: true`, esperar una lectura y comprobar en `procesos_portal_foto` y en las cards que los estados coinciden con la página. Verificar sin avisos de más en la primera foto.
- [ ] 5.3 👤 Repetir el piloto en Magneto, después de que `magneto-confirmar-y-leer-encuesta` esté verificado. Verificar igual que 5.2.
- [ ] 5.4 🟢 Archivar con `/opsx:archive` (después de `seguimiento-proceso-postulacion`). Verificar con `openspec validate` y `openspec list`.
