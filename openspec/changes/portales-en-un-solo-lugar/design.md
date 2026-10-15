## Context

Ver proposal.md (Why). Inventario medido el 2026-10-14 de dónde se repiten hoy los datos de un portal:

| Lugar | Qué guarda | Portales |
|---|---|---|
| `radar/formato.py` `NOMBRES_FUENTE` | nombre visible de la fuente (canal, resumen, reportero) | linkedin, computrabajo, elempleo, magneto, getonboard, torre, sena, spe |
| `asistente/vacantes.py` `PLATAFORMAS` | dominio → plataforma con postulación automática | computrabajo, magneto |
| `asistente/textos.py` `NOMBRES_PLATAFORMA` y `URL_REGISTRO` | nombre y página de inicio para el bot | computrabajo, magneto |
| `asistente/textos.py` `NAVEGADOR` y `asistente/tarjeta.py` | «Computrabajo y Magneto» escrito en el texto | computrabajo, magneto |
| `asistente/detalle.py` | selector CSS del texto de la oferta por dominio | computrabajo, getonbrd, linkedin |
| `extension/portales.js` | `DOMINIOS`, `NOMBRES`, `INGRESO`, `INICIO` | 6 portales, en el orden de las tarjetas del popup |
| `extension/popup.js` | `DESCRIPCION` y la lista de respaldo `computrabajo \|\| magneto` | 6 portales |
| `extension/manifest.json` | permisos fijos y opcionales | 6 portales |
| `config.yaml` | `fuentes.*` (8) y `asistente.plataformas` (2) | — |

Diferencias que hoy existen y se deben conservar:
- El SPE se llama «Servicio Público de Empleo» en el radar y «Servicio de Empleo» en la extensión.
- `torre` y `sena` son fuentes de `config.yaml` sin dominios ni presencia en la extensión.
- `detalle.py` compara con `host.endswith(dominio)` (sin punto), mientras `vacantes.py` y `portales.js` exigen el dominio exacto o un subdominio.

## Goals / Non-Goals

**Goals:**
- Un único archivo de datos de portales, validado, del que leen Python y la extensión.
- Pruebas que fallen ante cualquier copia desincronizada.
- Equivalencia exacta con el comportamiento actual.

**Non-Goals:**
- Unificar los nombres del SPE o cambiar cualquier texto visible.
- Generar el `manifest.json` o el texto de la política de privacidad.
- Registrar las clases de las fuentes del radar desde el YAML (siguen en `FUENTES` de `corrida.py`).
- Cambiar `ADAPTADORES` o `PROHIBIDAS` de `portales.js` (son lógica de la extensión, no datos del portal).
- Validar el registro en el arranque contra `config.yaml`. Se valida en pruebas para que un descuido no tumbe el servicio en el Fedora.

## Decisions

### 1. YAML en `assets/comun/portales.yaml`
El proyecto ya guarda datos editables en `assets/<paquete>/` (banco de preguntas, tecnologías, selectores). El registro lo usan el radar y el asistente, así que va en `assets/comun/`. El orden del archivo es el orden de las tarjetas del popup: computrabajo, magneto, elempleo, getonboard, linkedin, spe, torre, sena.

Forma de cada entrada:

```yaml
- id: spe
  nombre: Servicio Público de Empleo
  nombre_corto: Servicio de Empleo        # opcional; por defecto, nombre
  dominios: [buscadordeempleo.gov.co]      # opcional; sin dominios no va a la extensión
  inicio: https://www.buscadordeempleo.gov.co/
  ingreso: https://www.buscadordeempleo.gov.co/
  descripcion: Portal oficial de Colombia  # subtítulo del popup
  selector_oferta: null                    # selector CSS del texto de la oferta, si hace falta
  asistente: false                         # true: el asistente postula en él
```

*Alternativas descartadas:*
- **Módulo Python con constantes.** No lo puede leer la extensión sin un generador igual de complejo, y mezcla datos con código.
- **Sección en `config.yaml`.** Ese archivo ya tiene 1.349 líneas y es la configuración de operación. Estos datos son del dominio y cambian con el código.

### 2. `comun/portales.py` con pydantic y caché
- Modelo `Portal` (pydantic, `extra="forbid"`) y una lista validada.
- Errores que nombran el `id` y el campo; los identificadores repetidos se rechazan.
- Carga perezosa con `functools.cache`, igual que los demás `assets`.

Funciones:
- `portales()`: todos, en orden.
- `portal(id)`: uno, o `None` si no existe.
- `nombre(id)`: devuelve el identificador tal cual si no existe, como el `.get(f, f)` actual.
- `nombre_corto(id)`.
- `plataforma_de_url(url)`: solo los portales con `asistente: true`; dominio exacto o subdominio.
- `conectados()`.
- `lista_nombres(ids)`: «A», «A y B», «A, B y C».

Va en `comun/` porque lo usan el radar y el asistente; respeta la regla `comun ← asistente ← radar`.

### 3. Los módulos existentes conservan sus nombres públicos
Para no tocar llamadas ni pruebas, los símbolos actuales siguen existiendo y pasan a derivarse del registro:
- `NOMBRES_FUENTE`, `NOMBRES_PLATAFORMA` y `URL_REGISTRO` se construyen como `dict` al importar el módulo.
- `vacantes.PLATAFORMAS` y `vacantes.plataforma_de_url` hacen lo mismo.
- `textos.NAVEGADOR` se arma con `lista_nombres(conectados())` y produce el mismo texto.

`NOMBRES_PLATAFORMA` y `URL_REGISTRO` siguen limitados a los portales conectados, como hoy. Así `.get(...)` devuelve lo mismo para cualquier clave.

*Alternativa descartada:* reemplazar cada uso por llamadas a `portales.nombre(...)`. Es más limpio, pero toca unos 15 sitios de `conversacion.py`, `tarjeta.py` y `resumen_postulacion.py` y choca con `dividir-conversacion-asistente`. Se puede hacer después, cuando ese change esté cerrado.

### 4. `detalle.py` conserva su comparación por sufijo
Se pasa de un mapa local a uno construido desde `selector_oferta`, manteniendo `host.endswith(dominio)` tal cual. Si se cambiara a la comparación exacta, un host como `x-linkedin.com` dejaría de coincidir; es poco probable, pero sería un cambio de comportamiento. Unificar la comparación queda anotado como mejora futura.

### 5. Extensión: archivo generado y versionado
`extension/portales_datos.js` lleva al inicio la cabecera «Generado desde assets/comun/portales.yaml: no editar a mano» y exporta `DOMINIOS`, `NOMBRES`, `INGRESO`, `INICIO`, `DESCRIPCION` y `CONECTADOS`:
- `NOMBRES` toma el `nombre_corto` de cada portal.
- Solo entran los portales con dominios.
- El orden es el del YAML.

`portales.js` reexporta esos símbolos (los importadores no cambian) y `popup.js` toma `DESCRIPCION` y `CONECTADOS` de ahí en lugar de sus copias.

El generador es una función pura `generar_js(portales) -> str`, con salida determinista: comillas dobles, sangría de 2 espacios y un salto de línea final. Lo usan dos sitios:
- el subcomando `buscador.py asistente portales-js`, que escribe el archivo;
- la prueba de sincronía, que compara el texto en memoria con el archivo guardado.

*Alternativas descartadas:*
- **`import ... with { type: "json" }`.** Exige Chrome 123 y el manifiesto declara `minimum_chrome_version: 116`.
- **Pedir los datos al servidor.** La extensión debe mostrar los portales sin estar vinculada, y el popup ya funciona sin red.
- **Generarlo solo al empaquetar.** El archivo no estaría en el repositorio y la extensión cargada sin empaquetar (desarrollo, pruebas de Playwright) quedaría rota.

### 6. Pruebas de coherencia en `tests/comun/test_portales.py`
- **Equivalencia:** una copia literal de los mapas actuales, congelada en la prueba, se compara con lo que da el registro. Tras el cambio, esa copia es la única que queda y sirve para detectar regresiones.
- **Sincronía** del archivo JS.
- **Cobertura de `FUENTES` y `config.yaml`:** cada fuente tiene registro y cada plataforma de `asistente.plataformas` está conectada.
- **Permisos del manifiesto:** cada dominio con permiso fijo u opcional.
- **Política de privacidad:** el HTML de `api.py` nombra cada portal conectado.
- **Validación:** casos de nombre ausente y de identificador repetido.

Las pruebas de coherencia que leen `corrida.FUENTES` viven en `tests/radar/`, porque `tests/comun/` no debe depender del radar. Esto aplica la regla de paquetes también a las pruebas, aunque la prueba de arquitectura hoy solo revisa el código.

## Risks / Trade-offs

- [Un YAML roto tumba el radar y el asistente al arrancar] → Validación con mensaje claro y una prueba que carga el archivo real. El Fedora solo recibe cambios por `git pull` de `main` con la suite en verde.
- [Alguien edita `portales_datos.js` a mano] → La cabecera lo advierte y la prueba de sincronía falla.
- [Diferencia invisible al construir los mapas (orden, mayúsculas, espacios)] → La prueba de equivalencia compara carácter por carácter con la copia congelada.
- [Choque con `conectar-plataformas-extension`, que también toca `vacantes.py` y `textos.py`] → Este change va **antes** de sus tareas 3.1 y 3.2. Al terminar se reescribe el texto de esas tareas para que añadir elempleo sea editar `portales.yaml`.
- [Más indirección para leer un nombre] → Se conservan los símbolos públicos (decisión 3), así que el código que los usa no cambia.

## Migration Plan

1. Rama `portales-en-un-solo-lugar` desde `main`, con la suite en verde como base.
2. Primero se agregan el YAML, el módulo y la prueba de equivalencia, sin tocar ningún consumidor. Ese commit no cambia nada en ejecución.
3. Un commit por consumidor: radar, asistente y extensión, con la suite en verde tras cada uno.
4. Despliegue: `git pull --ff-only` en el Fedora y reinicio de `buscador-asistente`. El timer del radar toma el cambio en la siguiente corrida. La extensión publicada no necesita actualizarse, porque su comportamiento es idéntico; el próximo `.zip` incluirá el archivo generado.
5. Vuelta atrás: `git revert` del merge. No hay datos ni esquemas que migrar.
