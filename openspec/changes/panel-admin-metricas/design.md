## Context

- El servicio del asistente (`asistente/servicio.py`) ya levanta una app FastAPI con uvicorn en `asistente.api.host:puerto`, publicada con Tailscale Funnel en `url_publica`. Hoy toda ruta fuera de `/api/v1/` responde 404.
- El asistente ya abre `vacantes.db` en solo lectura (`asistente.vacantes_db`), así que puede leer `vistas`, `corridas`, `fuentes_estado` e `ia_uso` del radar sin tocar el proceso del radar.
- El radar corre con un timer de systemd cada 30 minutos (`radar/corrida.py`). Al final llama a `Estado.limpiar`, que borra `vistas` a los 90 días y `corridas`, `intentos` e `ia_uso` a los 30.
- Las fechas se guardan en UTC ISO-8601 (`estado.a_texto`). Colombia no cambia de hora, así que el día local es UTC−5 fijo, pero se usa `zoneinfo` para no depender de eso.
- Los comandos del dueño (`/usuarios`, `/stats`, `/plataformas`) se resuelven en `Conversacion` con `es_dueno`. `/stats` ya calcula cifras de 24 horas.

## Goals / Non-Goals

**Goals:**
- Que el panel exista sin agregar procesos, puertos ni dependencias de Python.
- Que las consultas de un mes o un rango de 366 días respondan en menos de 1 segundo en el PC Fedora.
- Que la base del panel sirva tal cual a `panel-admin-usuarios` y a `panel-admin-filtros`: estructura, sesión, CSRF y navegación.

**Non-Goals:**
- Editar configuración o datos (es `panel-admin-filtros`).
- Ver usuarios ni miembros del grupo (es `panel-admin-usuarios`).
- Alertas en tiempo real, exportar a CSV o PDF.
- Cambiar la clasificación del radar con el tipo de vacante: el tipo es solo para estadísticas.

## Decisions

### D1. El panel vive en la app FastAPI del asistente, bajo `/panel/`
Se monta un `APIRouter` en `crear_app`: `/panel/` sirve la página y `/panel/datos/...` sirve JSON. El 404 de cualquier otra ruta sigue igual.
- *Alternativa*: un servicio aparte en otro puerto. Exigiría otro Funnel, otra unidad de systemd y otra configuración, sin ganar nada.
- *Alternativa*: dejar el panel solo en la tailnet, sin Funnel. Los otros admins tendrían que entrar a la tailnet del dueño. Se descarta por ahora; la seguridad la da la sesión.

### D2. Entrada por enlace de un solo uso, sin contraseñas ni Telegram Login Widget
`/panel` genera un token con `secrets.token_urlsafe(32)`, guarda `sha256(token)` en `panel_sesiones` (tipo `enlace`, con su vencimiento) y envía el enlace por chat privado. El mensaje se programa como efímero con `mensajes_efimeros`. El canje marca el enlace como usado, dentro de la misma transacción, y crea una fila de tipo `sesion` con su propio hash y su token CSRF.
- *Alternativa*: Telegram Login Widget. Exige registrar el dominio en BotFather y cargar un script de `telegram.org`, lo que rompe la CSP de solo origen propio.
- *Alternativa*: usuario y contraseña. Habría más secretos que guardar y otra cosa que recordar. El bot ya es un canal autenticado.

La autenticación es un `Depends` que busca la sesión por el hash de la cookie, comprueba que no venció y que el id sigue siendo admin, y renueva `ultimo_uso`. Los admins se leen de la configuración cargada; cambiar la lista exige reiniciar el servicio, como el resto de `asistente`.

### D3. Página sin compilación: HTML, JS en módulos y Chart.js en el repositorio
`assets/asistente/panel/` contiene:
- `index.html`;
- `panel.css`;
- `panel.js` (router por `location.hash` para las secciones y `URLSearchParams` para el periodo);
- `chart.umd.min.js` en una versión fija, 4.4.x, con su licencia MIT.

FastAPI los sirve con `FileResponse` desde rutas explícitas, sin `StaticFiles` sobre un directorio. El estilo usa variables CSS con tema claro y oscuro y sirve en el celular (una columna bajo 768 px).
- *Alternativa*: React o Vue con Vite. Agregaría Node a la compilación y al despliegue en el Fedora.
- *Alternativa*: plantillas Jinja2. Los gráficos igual necesitan JS, y el JSON se puede probar directo con pytest.

### D4. Tablas de resumen diario en lugar de alargar la retención
Tabla nueva en `vacantes.db` (esquema 4 de `estado.py`):

```
metricas_dia(fecha TEXT, dimension TEXT, clave TEXT, metrica TEXT, valor INTEGER,
             PRIMARY KEY (fecha, dimension, clave, metrica))
```

- `dimension` ∈ {`total`, `fuente`, `categoria`, `tipo`, `modalidad`, `fuente_tipo`, `descarte`, `ia_tarea`}.
- `clave` es, por ejemplo, `computrabajo`, `computrabajo|aprendiz_sena` o `seniority`.
- `metrica` ∈ {`vistas`, `publicadas`, `corridas`, `corridas_error`, `crudas`, `duplicadas`, `dudosas`, `ia_aceptadas`, `ia_rechazadas`, `enviadas`, `llamadas`, `errores`, `tokens_in`, `tokens_out`}.

Un esquema largo (filas, no columnas) permite agregar métricas sin migraciones. `comun/metricas.py` tiene `resumir_dia(cx, fecha, config)`: en una transacción hace `DELETE` de la fecha y luego `INSERT` desde `vistas`, `corridas` e `ia_uso`. `corrida.py` lo llama para hoy y para ayer **antes** de `limpiar`. La limpieza borra además las filas de `metricas_dia` con más de `dias_metricas` días.

El asistente tiene su tabla `metricas_dia_asistente`, con la misma forma, en `asistente.db` (esquema 4 de `datos.py`). La recalcula `tareas_periodicas` una vez por hora, a partir de `postulaciones`, `ia_uso` y `usuarios`.
- *Alternativa*: subir `dias_vistas` a 730. Haría crecer `vistas` y el JSON de `por_enviar` sin control, y no cubre `corridas` ni `ia_uso`.
- *Alternativa*: que el asistente calcule el resumen del radar. Necesitaría escribir en `vacantes.db`, que hoy abre en solo lectura, y competir con el radar por el bloqueo.

### D5. Una sola consulta por vista según el periodo
`panel/consultas.py` resuelve el periodo a `[desde, hasta)` en UTC, con `zoneinfo("America/Bogota")`, y elige la fuente de datos:
- **Totales y series diarias**: siempre desde `metricas_dia` y `metricas_dia_asistente`. Son rápidos y valen para cualquier fecha.
- **Series por hora y listas de vacantes**: desde `vistas` y `corridas`, solo si el periodo está dentro de la retención del detalle. Si no lo está, la respuesta trae `detalle_disponible: false` y el JS muestra el aviso.
- **Hoy**: el resumen de hoy se recalcula en cada corrida, así que puede tener hasta 30 minutos de atraso. La portada indica «actualizado a las HH:MM» con la hora de la última corrida.

Cada respuesta JSON trae `periodo`, `anterior` (las mismas cifras del periodo anterior) y `series`. El JS calcula la variación en porcentaje, para que la regla esté en un solo sitio: el servidor manda los dos valores y la plantilla los formatea.

### D6. Tipo de vacante en `comun/metricas.py`, configurable en `asistente.panel.tipos`
`tipo_de(titulo, tipos)` reutiliza la normalización de `radar/filtros.py` (minúsculas, sin tildes, límites de palabra) para no tener dos criterios. Orden por defecto:
1. `aprendiz_sena` (sena, aprendiz sena, adso, etapa productiva, contrato de aprendizaje);
2. `aprendiz`;
3. `practicante` (practicante, práctica, prácticas, práctica profesional);
4. `pasantia` (pasante, pasantía);
5. `trainee`;
6. `intern` (intern, internship, becario);
7. `junior` (junior, jr, entry level, sin experiencia, recién egresado);
8. `otro` si no coincide ninguno.

### D7. Configuración nueva
```yaml
asistente:
  panel:
    activo: false
    admins: []          # ids de Telegram además del dueño
    enlace_min: 5
    sesion_h: 8
    dias_metricas: 730
    tipos: [...]        # D6
```
Se valida con un modelo `AsistentePanel` en `comun/config.py`. Si `activo` es true pero el asistente está inactivo o no hay `url_publica`, la carga de la configuración falla con un mensaje claro.

## Risks / Trade-offs

- [El panel queda expuesto en Internet por el Funnel] → El enlace es de un solo uso, vence en 5 minutos y el token tiene 256 bits. Además: cookie `Secure` y `SameSite=Strict`, CSP sin terceros, límite por IP, auditoría y `activo: false` por defecto.
- [Alguien reenvía el enlace del chat de un admin] → Sirve una sola vez y el mensaje se borra a los 5 minutos. El admin ve en la auditoría cuándo se usó.
- [El resumen de hoy se atrasa hasta 30 minutos] → La hora de la última actualización se muestra en pantalla. Calcular hoy en vivo desde `vistas` es posible, pero obligaría a mezclar dos fuentes en cada gráfico.
- [El resumen diario hace más lenta la corrida] → Son dos días con agregados simples sobre índices existentes, del orden de milisegundos. Si hace falta se agrega un índice `vistas(enviada_en)`.
- [El tipo por título se equivoca en títulos raros] → Es solo estadístico y la lista es configurable. La categoría del radar no cambia.
- [Chart.js guardado en el repositorio queda desactualizado] → La versión está fija y anotada en `assets/asistente/panel/LICENCIA-chartjs.txt`. Actualizarla es reemplazar un archivo.

## Migration Plan

1. Desplegar con `asistente.panel.activo: false`. El radar migra `vacantes.db` al esquema 4 y rellena el resumen con el detalle que queda. El asistente migra `asistente.db`.
2. Revisar en los logs del radar que el relleno terminó, y contar las filas de `metricas_dia`.
3. Poner `activo: true` y los `admins`, reiniciar `buscador-asistente.service` y probar `/panel` desde el Telegram del dueño.
4. Vuelta atrás: `activo: false` y reiniciar. Las tablas nuevas no estorban al código anterior, porque `CREATE TABLE IF NOT EXISTS` y la versión de esquema solo suben.
