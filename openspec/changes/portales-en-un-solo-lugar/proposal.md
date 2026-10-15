## Why

Los datos de cada portal (nombre, dominios, páginas de inicio e ingreso) están copiados a mano en unos diez lugares del radar, del asistente y de la extensión. Algunos ya no coinciden: el SPE se llama «Servicio Público de Empleo» en el radar y «Servicio de Empleo» en la extensión, y los textos del bot dicen «Computrabajo y Magneto» escrito a mano. El próximo paso del asistente es conectar elempleo (`conectar-plataformas-extension`, tareas 3.1 y 3.2), y con la estructura actual eso obliga a tocar cada copia sin que nada avise si falta una. Conviene juntar esos datos **antes** de sumar el portal, sin cambiar lo que ve el usuario.

## What Changes

- Un archivo único `assets/comun/portales.yaml` con un registro por portal: identificador, nombre, nombre corto, dominios, página de inicio, página de ingreso, descripción para el popup, selector del texto de la oferta y si el asistente postula en él.
- Un módulo `buscador_vacantes/comun/portales.py` que carga y valida ese archivo (pydantic) y ofrece consultas: `portal(id)`, `nombre(id)`, `plataforma_de_url(url)`, `conectados()` y `lista_nombres(...)`.
- El radar y el asistente leen de ese módulo en lugar de sus copias:
  - `radar/formato.py` (`NOMBRES_FUENTE`);
  - `asistente/vacantes.py` (`PLATAFORMAS` y `plataforma_de_url`);
  - `asistente/textos.py` (`NOMBRES_PLATAFORMA`, `URL_REGISTRO` y el texto `NAVEGADOR`);
  - `asistente/tarjeta.py` (línea «Inicia sesión en Computrabajo y Magneto»);
  - `asistente/detalle.py` (selectores del texto de la oferta por dominio).
- La extensión recibe los datos en un archivo **generado** `extension/portales_datos.js`. `portales.js` y `popup.js` importan de él y conservan su lógica. Un comando genera el archivo y una prueba falla si el archivo guardado no coincide con el YAML.
- Pruebas de coherencia sobre el repositorio:
  - cada fuente de `radar/corrida.py` (`FUENTES`) y de `config.yaml` tiene registro;
  - cada plataforma de `config.yaml` (`asistente.plataformas`) es un portal conectado;
  - cada portal con dominios está en los permisos del `manifest.json`;
  - la política de privacidad nombra a cada portal conectado.
- **Sin cambios de comportamiento.** Los mismos textos, nombres, enlaces y mapeos de dominio que hoy, carácter por carácter. Tampoco cambian `config.yaml`, los esquemas SQLite, el contrato de la API ni la versión de la extensión.
- **Fuera de alcance:**
  - el `manifest.json`, que sigue a mano porque cambiarlo exige revisión de la tienda;
  - el texto legal de la política de privacidad, que sigue a mano porque tiene fecha;
  - la clase de cada fuente del radar (`FUENTES`), que es código;
  - `radar/migrar_historial.py` (migración histórica);
  - conectar elempleo, que es trabajo de `conectar-plataformas-extension`.

## Capabilities

### New Capabilities
- `registro-portales`: fuente única de los datos de cada portal para el radar, el asistente y la extensión, con pruebas que detectan copias desincronizadas, y equivalencia de comportamiento con los mapas actuales.

### Modified Capabilities

## Impact

- **Código Python:** `comun/portales.py` (nuevo), `radar/formato.py`, `asistente/vacantes.py`, `asistente/textos.py`, `asistente/tarjeta.py`, `asistente/detalle.py` y `asistente/cli.py` (subcomando para generar el JS).
- **Extensión:** `extension/portales_datos.js` (nuevo, generado), `extension/portales.js` y `extension/popup.js`. Los archivos de la extensión y su versión no cambian para el usuario; el `.zip` lleva un archivo más.
- **Datos:** `assets/comun/portales.yaml` (nuevo).
- **Pruebas:** `tests/comun/test_portales.py` (nuevo) y ajustes en las pruebas que importan los mapas antiguos.
- **Despliegue:** ninguno especial. El Fedora solo necesita `git pull` y reiniciar `buscador-asistente`. El radar lee el YAML en cada corrida.
- **Changes abiertos:** `conectar-plataformas-extension` (tareas 3.1 y 3.2) se simplifica: añadir elempleo pasa a ser editar `portales.yaml`. Se actualiza el texto de esas tareas.
- **Riesgo:** un error de formato en `portales.yaml` rompería el radar y el asistente al arrancar. Mitigación: validación con pydantic, mensaje claro y prueba que carga el archivo real del repositorio.
