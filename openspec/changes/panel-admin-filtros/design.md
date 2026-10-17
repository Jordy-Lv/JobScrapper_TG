## Context

- `cargar_configuracion` (`comun/config.py`) ya combina `config.yaml` con `config.local.yaml` mediante `_combinar`. Esa función mezcla diccionarios de forma recursiva y reemplaza listas y valores sueltos. Se valida con pydantic (`Configuracion`).
- El Fedora se actualiza con `git pull` (`deploy/INSTALAR.md`). Si el panel escribiera `config.yaml`, el siguiente pull chocaría.
- El radar carga la configuración en cada corrida (timer de 30 minutos). El asistente la carga al arrancar.
- `Filtros(cfg.Filtros).evaluar(vacante)` aplica las reglas sin efectos externos.
- `vistas` guarda las vacantes aceptadas por reglas, las dudosas y las enviadas, pero no las rechazadas. El texto de detalle está en `detalles` (15 días).
- Hay que confirmar que el radar y el asistente corren con el mismo usuario y la misma carpeta del proyecto en el Fedora (tarea 5.2).

## Goals / Non-Goals

**Goals:**
- Que ningún cambio desde el panel pueda dejar al radar sin arrancar.
- Que el panel no toque archivos versionados en git.
- Que la prueba use exactamente la misma lógica de filtros que el radar.

**Non-Goals:**
- Editar prompts de IA, secretos, Telegram, red, ritmo de LinkedIn, detalle u opciones de las fuentes.
- Editar la configuración del asistente (topes, plataformas, proveedores de IA). `/plataformas` sigue existiendo.
- Aplicar el cambio al instante con una corrida forzada.

## Decisions

### D1. Capa `config.panel.yaml` sobre las otras dos, con lista blanca de claves
`cargar_configuracion` agrega una tercera capa después de `config.local.yaml`.
- *Por qué después*: lo que el admin guarda en el panel debe verse reflejado aunque `config.local.yaml` tenga otro valor. `config.local.yaml` es para lo propio del PC (bot, URL, rutas), que el panel no toca.
- *Lista blanca*: `CLAVES_PANEL` recorre el YAML y rechaza cualquier ruta fuera de `palabras_clave`, `filtros` y los cuatro campos de cada fuente.
- *Capa inválida*: el modelo se valida primero con las tres capas y, si falla, con dos. En ese caso se escribe el error en el log y, en el radar, se encola un aviso al dueño con un hash del contenido guardado en `kv`, para no repetirlo.
- *Alternativa*: editar `config.yaml` con `ruamel.yaml` para conservar los comentarios. Choca con `git pull`, mezcla los cambios del dueño con los del repositorio y agrega una dependencia.
- *Alternativa*: guardar los filtros en SQLite. Partiría la fuente de verdad en dos y obligaría a cambiar cómo el radar arma `Filtros`.

### D2. Escritura atómica y control de versión optimista
`edicion.guardar(secciones, version_base, actor, comentario)`:
1. lee `config.panel.yaml` y calcula su hash;
2. si el hash no coincide con `version_base`, el que tenía el editor al abrir, responde 409;
3. combina las secciones nuevas;
4. valida con `cargar_configuracion` sobre una carpeta temporal con las tres capas;
5. escribe `config.panel.yaml.tmp`, hace `fsync` y luego `os.replace`;
6. inserta la versión en `config_versiones` (id, ts, actor, comentario, contenido, hash, diferencias) en `asistente.db`.

El archivo es la fuente de verdad y la tabla es el historial. Al arrancar, si el archivo no coincide con la última versión (porque alguien lo editó a mano), se registra una versión «editada fuera del panel».

### D3. Prueba con `Filtros.evaluar` sobre las vacantes recientes
`edicion.probar(secciones)`:
1. arma dos `Filtros`, el vigente y el editado;
2. reconstruye `Vacante` desde `vistas` y `descartadas` de los últimos `dias_prueba` días, con la descripción de `detalles` cuando existe;
3. evalúa cada vacante con los dos `Filtros` y devuelve solo las que cambian de resultado o de categoría, junto con los totales.

La fecha de publicación se toma de `primera_vez`, para que la regla de antigüedad no rechace todo. Son unos pocos miles de vacantes como máximo, así que se hace en el momento, sin caché, con un límite de 10 s.
- *Limitación*: sin la descripción completa, las reglas que dependen de ella (guardarraíl de prácticas, modalidad) pueden diferir del radar real. El panel lo indica en la prueba.

### D4. Tabla `descartadas` en `vacantes.db`
```
descartadas(clave TEXT PRIMARY KEY, fuente TEXT, titulo TEXT, empresa TEXT, url TEXT,
            ubicacion TEXT, modalidad TEXT, motivo TEXT, ts TEXT NOT NULL)
```
La tabla es del esquema 5 de `estado.py`. Se escribe con `INSERT ... ON CONFLICT(clave) DO UPDATE SET ts, motivo` en `corrida.py`, en el mismo punto donde hoy se cuentan los descartes. `Estado.limpiar` borra las de más de `dias_prueba` días. No guarda datos personales: son ofertas públicas.

### D5. Editor en la página
- Un componente de chips por lista, con normalización en JS igual a la de Python (minúsculas, NFD sin diacríticos) para el aviso de repetidos. El servidor vuelve a validar.
- Las áreas se reordenan arrastrando y soltando nativo, con botones ↑ y ↓ para teclado y celular.
- Las diferencias se muestran por sección: términos agregados en verde, quitados en rojo, números con «antes → después».
- La edición sin guardar queda en `sessionStorage`, para no perderla al recargar tras un 409.

### D6. Límites de las fuentes en el panel
Además del modelo, el panel aplica estos límites (constantes en `edicion.py`): `presupuesto` de 0 a 20, `reservado_nucleo` de 0 a `presupuesto` y `paginas_nucleo` de 1 a 5. Así se evita, por error, una corrida que dispare los bloqueos de los portales. Para valores fuera de esos límites queda `config.yaml`.

## Risks / Trade-offs

- [Un admin desactiva todas las fuentes o vacía el núcleo] → El modelo ya exige listas no vacías. El panel avisa antes de guardar si quedan 0 fuentes activas, y el historial permite restaurar en un clic.
- [`config.panel.yaml` y `config.yaml` se desalinean: el repositorio agrega un término y el panel tiene la sección entera] → Cada sección marca su origen. Si la sección del repositorio cambió después de la versión del panel, el panel lo avisa con «el repositorio cambió esta sección; revisa o vuelve al valor del repositorio».
- [La prueba no es idéntica al radar] → Se indica en pantalla. Las dudosas se informan como «irían a la IA», sin simular su veredicto.
- [El asistente necesita escribir en la carpeta del proyecto] → Es el mismo usuario de systemd. Se documenta y se comprueba con la tarea del dueño. SELinux no lo impide en `$HOME`.

## Migration Plan

1. Desplegar después de `panel-admin-metricas`. El radar sube `vacantes.db` al esquema 5 y empieza a guardar `descartadas`. La prueba da resultados completos después de `dias_prueba` días.
2. Agregar `config.panel.yaml` a `.gitignore` antes del primer guardado.
3. Vuelta atrás: borrar `config.panel.yaml` devuelve todo a `config.yaml`. El código anterior no lee esa capa.
