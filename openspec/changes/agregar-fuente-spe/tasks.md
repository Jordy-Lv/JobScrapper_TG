# Tasks

## 1. Certificado intermedio

- [x] 1.1 Descargar el intermedio "GeoTrust TLS RSA CA G1" de `cacerts.digicert.com` a `assets/certs/geotrust-tls-rsa-ca-g1.pem` y verificar que su huella SHA-256 coincide con la publicada por DigiCert. En el servidor, comprobar con `openssl s_client -CAfile <certifi + pem>` que la cadena de buscadordeempleo.gov.co verifica ("Verify return code: 0").

## 2. Fuente SPE

- [x] 2.1 Crear `buscador_vacantes/fuentes/spe.py`:
  - `nombre = "spe"`, `consulta_fija`, `soporta_paginas = True`, `tamano_pagina = 50`.
  - Cliente httpx con un contexto TLS que carga certifi y el PEM.
  - `construir_peticion` con `page` y `PLAZA_PRACTICA=1`.
  - `parsear` con el mapeo al origen, la limpieza de "PL-", los campos del design y el descarte de plazas vencidas, sin URL o cuyo enlace exige login (`opciones.dominios_con_login` y rutas con `login`/`auth/`); lanza `CambioHTML` si falta `resultados`.

  Verificar con `tests/test_spe.py` sobre un fixture JSON real (`tests/fixtures/spe_practicas.json`, recortado a ~10 plazas con casos de elempleo, Magneto, universidad, vencida, sin URL y con enlace de login): claves `elempleo:`/`magneto:`/`spe:`, URL original, título sin "PL-", empresa vacía, ubicación, salario, modalidad y descartes.
- [x] 2.2 Soporte de consulta fija en `corrida._consultar`: si la clase tiene `consulta_fija`, el lote son sus páginas 1..presupuesto y la rotación no avanza. Verificar con una prueba en `tests/test_buscador.py` (lote de páginas 1–2, sin cambio en la tabla `rotacion`).
- [x] 2.3 Registrar `spe` en `corrida.FUENTES` y `formato.NOMBRES_FUENTE` ("Servicio Público de Empleo"). Verificar que `uv run pytest`, `uv run ruff check` y `uv run ruff format --check` pasan.

## 3. Configuración y documentación

- [x] 3.1 Agregar `fuentes.spe` (activa, presupuesto 2, reservado_nucleo 1, filtra_nivel true, `opciones.dominios_con_login`, con una nota del origen) y `spe` a `ubicacion.fuentes_colombianas` en `config.yaml`. Verificar con `tests/test_config.py` que la fuente carga y es colombiana.
- [x] 3.2 Agregar el Servicio Público de Empleo a la lista de fuentes del `README.md` y explicar el mapeo al origen y el certificado intermedio. Verificar que coincide con `config.yaml`.

## 4. Despliegue

- [x] 4.1 Commit y push (sin atribución a IA), `git pull` en el servidor y `uv run buscador.py --dry-run --fuente spe` en el servidor. Verificar que el request responde 200 con verificación TLS y revisar cuántas plazas pasan los filtros.
- [x] 4.2 Verificar en el log de la siguiente corrida normal que `spe` aparece con 2 requests 200 y que sus vacantes enviadas no repiten claves ya enviadas por elempleo o Magneto.
