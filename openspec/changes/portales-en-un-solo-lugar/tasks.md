## 1. Precondiciones

- [ ] 1.1 🟢 Confirmar que `arreglar-pruebas-en-windows` está cerrado y unido a `main`, y que no hay trabajo sin confirmar en `asistente/vacantes.py`, `textos.py`, `tarjeta.py`, `detalle.py`, `radar/formato.py` ni `extension/`. Verificar con `git status` limpio en esos archivos.
- [ ] 1.2 🟢 Crear la rama `portales-en-un-solo-lugar` desde `main` y anotar aquí la línea base. Verificar con la salida de `uv run pytest -q` (pasan, fallan y omitidas) y `uv run ruff check`.

## 2. Registro y módulo (sin consumidores)

- [ ] 2.1 🟡 Crear `assets/comun/portales.yaml` con las 8 entradas en el orden de la decisión 1 del `design.md`. Copiar los valores literales de los mapas actuales: el `nombre_corto` del SPE, `asistente: true` solo en computrabajo y magneto, y `selector_oferta` en computrabajo, getonboard y linkedin. Verificar con la tarea 2.3.
- [ ] 2.2 🟡 Crear `buscador_vacantes/comun/portales.py` con el modelo pydantic y las funciones de la decisión 2. Verificar con pruebas en `tests/comun/test_portales.py`:
  - la carga del archivo real;
  - `nombre` de un id desconocido devuelve el id;
  - `plataforma_de_url` con subdominio, dominio ajeno y portal no conectado;
  - `lista_nombres` con 1, 2 y 3 nombres;
  - errores por nombre ausente y por id repetido, con mensajes que nombran el portal y el campo.
- [ ] 2.3 🟡 Prueba de equivalencia: congelar en la prueba una copia literal de `NOMBRES_FUENTE`, `PLATAFORMAS`, `NOMBRES_PLATAFORMA`, `URL_REGISTRO`, los selectores de `detalle.py` y `DOMINIOS`, `NOMBRES`, `INGRESO`, `INICIO` y `DESCRIPCION` de la extensión, y compararlos con el registro. Verificar con la prueba en verde y con que falla si se cambia una letra del YAML.
- [ ] 2.4 🟢 Commit «Registro único de portales (sin consumidores)». Verificar con la suite en verde y `ruff check` limpio.

## 3. Consumidores en Python

- [ ] 3.1 🟢 `radar/formato.py`: construir `NOMBRES_FUENTE` desde el registro. Verificar con `tests/radar/` en verde (formato, resumen y reportero) sin tocar aserciones.
- [ ] 3.2 🟡 `asistente/vacantes.py`: `PLATAFORMAS` y `plataforma_de_url` desde el registro, con solo los portales conectados. Verificar con `tests/asistente/test_detalle.py::test_plataforma_de_url` sin cambios.
- [ ] 3.3 🟡 `asistente/textos.py` y `asistente/tarjeta.py`:
  - `NOMBRES_PLATAFORMA` y `URL_REGISTRO` desde el registro;
  - `NAVEGADOR` y la línea «Inicia sesión en …» armados con `lista_nombres(conectados())`.

  Verificar con una prueba que compara `NAVEGADOR` con el texto anterior literal, y con `tests/asistente/` en verde.
- [ ] 3.4 🟢 `asistente/detalle.py`: el mapa de selectores desde `selector_oferta`, conservando `host.endswith(dominio)` (decisión 4). Verificar con `tests/asistente/test_detalle.py` sin cambios.
- [ ] 3.5 🟢 Revisar con `grep` que no quedan nombres ni dominios de portal escritos a mano en `buscador_vacantes/`, salvo las exclusiones de los Non-Goals del `design.md` (`corrida.FUENTES`, `migrar_historial.py`, la política de privacidad de `api.py` y los selectores de `fuentes/`). Verificar con la salida del `grep` anotada aquí.

## 4. Extensión

- [ ] 4.1 🟡 `generar_js(portales)` en `comun/portales.py` y el subcomando `buscador.py asistente portales-js` en `asistente/cli.py`, que escribe `extension/portales_datos.js`. Verificar con el archivo generado y con una prueba de sincronía que falla si se edita el archivo a mano.
- [ ] 4.2 🟡 `extension/portales.js`: importar y reexportar `DOMINIOS`, `NOMBRES`, `INGRESO` e `INICIO` desde `portales_datos.js`. `extension/popup.js`: usar `DESCRIPCION` y `CONECTADOS` en lugar de su copia y de `p === "computrabajo" || p === "magneto"`. Verificar con `test_sin_codigo_remoto` y con las pruebas `navegador` del popup y de la vinculación (`uv run pytest tests/asistente/test_extension.py -m navegador`).
- [ ] 4.3 🟢 `empaquetar-extension` incluye el archivo nuevo. Verificar listando el `.zip` generado.

## 5. Coherencia

- [ ] 5.1 🟡 Pruebas de coherencia (decisión 6). Verificar con cada prueba en verde y con que falla al quitar a propósito una entrada o un permiso:
  - `config.yaml` (`fuentes` y `asistente.plataformas`), en `tests/comun/`;
  - `manifest.json` y la política de privacidad, en `tests/asistente/`;
  - `corrida.FUENTES`, en `tests/radar/`.
- [ ] 5.2 🟢 Documentar en `README.md` (sección de desarrollo) cómo se agrega un portal: editar `portales.yaml`, ejecutar `portales-js` y revisar `manifest.json`. Verificar leyendo la sección.

## 6. Verificación y planes abiertos

- [ ] 6.1 🟡 Suite completa y `ruff check` / `ruff format --check`. La suite tarda unos 11 minutos: lanzarla en segundo plano y no tocar archivos mientras corre. Verificar con el mismo resultado que la línea base de 1.2, más las pruebas nuevas.
- [ ] 6.2 🟡 Corrida local en modo prueba (`uv run buscador.py --dry-run`) y `asistente servicio` sin red real. Verificar que los nombres de fuente del resultado y los textos del bot son los mismos que en `main`.
- [ ] 6.3 🟢 Reescribir las tareas 3.1 y 3.2 de `conectar-plataformas-extension` (y la decisión 6 de su `design.md`) para que añadir elempleo sea poner `asistente: true` en `portales.yaml` y regenerar el JS. Verificar leyendo el `tasks.md` actualizado, sin tocar tareas ya marcadas.

## 7. Cierre (👤)

- [ ] 7.1 👤 El dueño confirma unir a `main` y desplegar. Verificar con su respuesta.
- [ ] 7.2 👤 `git pull --ff-only` en el Fedora y reinicio de `buscador-asistente`. Verificar con la siguiente corrida del radar sin errores, el servicio activo y un ⚡ de prueba con el mismo texto de siempre.
