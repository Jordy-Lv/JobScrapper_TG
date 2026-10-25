## Context

- El motor actual (`extension/motor.js`) ejecuta **un paso declarado por llamada**: `detectar`, `esperar`, `clic`,
  `enviar`, `ir`, `formulario`, `llenar`, `cv_*` y `confirmar`. El service worker (`extension/servicio.js`)
  recorre la lista `postular` de `assets/asistente/selectores/<plataforma>.json`. Un paso que no encuentra su
  elemento devuelve `formulario_desconocido` y la postulación termina.
- `leerCampos` ya resuelve etiquetas (`label[for]`, etiqueta envolvente, `aria-label`, `aria-labelledby`,
  título del bloque, `placeholder`) y lo obligatorio (`required`, `aria-required`, `data-val-*`, «*»).
  `asignarValor` usa el *setter* nativo, que funciona con React. No lee controles ARIA ni iframes.
- `hayCaptcha` solo cuenta un elemento **visible** (`buscar` filtra por `visible`), así que un reCAPTCHA
  invisible no detiene hoy los flujos declarados.
- El servidor resuelve en `POST /postulaciones/{id}/formulario` con `respuestas.resolver` (tipo y `name` →
  aprendidas → consentimiento → banco → clasificación con IA → redactor). La IA corre con la clave de cada
  usuario por `ClienteIA` (6 proveedores en `config.yaml`, cada uno con todas las tareas de `cfg.NombreTarea`).
- En Computrabajo, elempleo (variante normal) y Magneto, **el clic de postular ya envía** (pasos con
  `envia: true` o el primer clic de «Aplicar»). Eso limita lo que el modo ensayo puede recorrer en esos
  portales.
- El reconocimiento de los ATS está en `docs/asistente/portales.md`, sección «LinkedIn».
- `familia_de(url, familias)` es la tarea 2.2 de `medir-destinos-linkedin`.

## Goals / Non-Goals

**Goals:**
- Un bucle genérico guiado por datos: las listas de textos de botones, de éxito y de barreras llegan del
  servidor, como los selectores, para afinarlas sin publicar otra versión de la extensión.
- Que la IA decida lo mínimo y nunca actúe fuera de una lista cerrada.
- Aprender de cada éxito y de cada reparación sin guardar datos personales.

**Non-Goals:**
- El permiso amplio de la extensión, la plataforma «externa», el clasificador de destino de LinkedIn y los
  lectores de esquema de cada ATS: son de `postular-linkedin`.
- Resolver captchas, crear cuentas o escribir credenciales.
- Que la IA escriba selectores o código: los selectores de recetas y parches los calcula la extensión sobre
  elementos reales.

## Decisions

### 1. La extensión observa y actúa; el servidor decide
Por cada pantalla, la extensión manda `POST /postulaciones/{id}/pantalla` con la clase que sugieren las
reglas, el esquema de campos, los botones clasificados y el **resumen sin valores** (lista numerada de
elementos visibles e interactivos: índice, rol, texto recortado, tipo y si está dentro del contenedor;
encabezados y avisos; máximo 150 elementos y 12 KB). El servidor responde una **decisión**: clase final,
respuestas por índice de campo y la acción siguiente (`avanzar`/`enviar` con índice de botón, `esperar`,
`cerrar_modal`, `respaldo` con motivo o `terminar` con estado). `/formulario` sigue para los flujos
declarados y para las extensiones viejas. Internamente, `/pantalla` reutiliza `resolver` y
`redactar_formulario`.

*Contrato de `/pantalla` (lo que implementa `bucleGenerico`).* Petición: `numero`, `clase`, `motivo`,
`idioma`, `url`, `campos` (el esquema de `leerPantalla`), `botones`, `sugerido` (`{indice, accion}` o
`null`), `firma`, `resumen`, `exito` y `correccion` (`true` en la vuelta única tras un error de
validación). Respuesta: `esperar_usuario` (la card pregunta lo que falta), `respuestas`
(`[{indice, valor|opcion|documento}]`), `cv_url`/`cv_nombre` (el CV cuando hay campo de archivo),
`documentos` (`{tipo: {url, nombre}}`, los demás archivos que piden los campos) y
`accion` con `tipo` ∈ `avanzar` | `enviar` (con `indice` de botón), `esperar` (`ms`), `exito`
(`texto`; solo vale con el envío registrado), `respaldo` (`motivo`) o `terminar` (`estado`,
`motivo`). Una respuesta sin `accion`, o con una desconocida, detiene el bucle sin pulsar nada. Las
pantallas `exito` y `barrera` las resuelve la extensión sin preguntar; `cerrar_modal` llega con
`/reparar`, que necesita pulsar por el índice del resumen.

*Alternativa descartada:* que la extensión llame a la IA directamente. Las claves viven cifradas en el
servidor, y la cola, las recetas y el registro de pasos también.

### 2. Reglas como datos versionados
`assets/asistente/motor_generico.json` (versionado como los selectores y entregado en el latido) trae los
textos por idioma de `avanzar`, `enviar`, `nunca`, `intermedia`, `exito`, `barrera` y `cookies_rechazar`,
los patrones de URL de éxito, los nombres trampa y los selectores de desafíos de captcha. La extensión no
trae listas propias, salvo las mínimas de seguridad: contraseña, `autocomplete` de contraseña y la
prohibición de campos ocultos. Esas no se pueden apagar desde el servidor.

### 3. Controles ARIA
- Combobox o listbox con opciones perezosas: foco, `ArrowDown` (o clic) y lectura de `[role=option]` del
  `aria-controls` o del último `listbox` visible, y `Escape`. Si hay más de 100 opciones o el campo es de
  búsqueda (`aria-autocomplete=list`), solo se manda `busqueda: true`. Para llenar se escribe el valor, se
  espera hasta 3 s por las opciones y se pulsa la que mejor coincide (igual normalizado, luego «empieza
  por»). Se comprueba leyendo el texto mostrado del control o el valor del `<input>` oculto que lo acompaña.
- Radios y casillas ARIA: clic y comprobación de `aria-checked`. Botones con `aria-haspopup=listbox`
  (Workday) como combobox.

### 4. Árbitro y reparación con salida cerrada
Hay dos tareas nuevas en `cfg.NombreTarea`, configuradas en los 6 proveedores con el modelo ligero,
temperatura 0 y unos 800 tokens de salida:
- `entender_pagina` → `DecisionPagina{clase, acciones: [{indice, accion, opcion?}], motivo}`.
- `reparar_flujo` → lo mismo, más `diagnostico` (texto corto para el dueño).
`accion` es un `Literal` cerrado y cada índice se valida contra el resumen enviado. Tope de 6 llamadas al
árbitro y 2 reparaciones por postulación (`asistente.motor_generico`). El texto de la página va como datos con
`INSTRUCCION_DATOS`.

*Alternativa descartada:* una captura de pantalla para un modelo con visión. Cuesta más tokens, no todos los
proveedores la aceptan y la captura puede mostrar datos del usuario. Queda para después, tomada antes de
llenar.

### 5. Selectores estables calculados por la extensión
Cuando una acción del árbitro o de la reparación funciona, la extensión calcula para ese elemento un selector
estable, en este orden: `id` no generado, `name`, `data-automation-id`/`data-qa`/`data-testid`, `aria-label`
o `{css, texto}` con el texto visible. Las recetas y los parches guardan ese selector. La IA nunca lo escribe.

### 6. Recetas
Tabla `recetas(host, ruta_patron, familia, firma, receta_json, exitos, fallos_seguidos, activa, origen,
actualizada)`. La firma de una pantalla es el conjunto de claves de sus campos (`nombre` o texto normalizado).
Una receta aplica si comparte al menos el 80 % de las claves. Se crea o refuerza solo con `enviada` y señal
explícita. El ensayo crea recetas `origen: ensayo`, que sirven para el mapeo y los botones, pero no para la
señal de éxito. El trabajo lleva la receta del host o, si no hay, la mejor de su familia.

### 7. Respaldo genérico de los flujos declarados y parches candidatos
En `ejecutarPaso`, un resultado `formulario_desconocido` **sin envío registrado** (`contexto.envio`) cambia a
`bucleGenerico(tab, contexto)` desde la pantalla actual, si `asistente.motor_generico.respaldo_declarado`
está encendido. Si termina `enviada`, el servidor guarda en `parches_flujo(plataforma, paso, selector_json,
estado: candidato|firme|descartado, exitos)` el selector que reemplaza al que falló. El trabajo siguiente de
esa plataforma recibe los selectores con el parche **antepuesto** a la lista del paso. El JSON revisado no se
toca: el dueño recibe el parche y lo copia a mano.

### 8. Iframes
`executeScript({target: {tabId, allFrames: true}})` inyecta el motor en todos los marcos con permiso. Una
primera lectura elige el marco con más campos visibles, y las siguientes llamadas van a ese `frameId`.
`paginaPermitida` se aplica al URL del marco.

### 9. Idioma
La extensión manda `document.documentElement.lang`. El servidor lo confirma contando palabras frecuentes de
es/en/pt en las etiquetas, porque muchos sitios declaran `lang="en"` aunque estén en español. El redactor
recibe el idioma como dato.

### 10. Documentos extra y carta en archivo
`documentos_usuario(usuario_id, tipo, nombre, ruta_cifrada, bytes, creado)`, con los archivos cifrados con
`cifrado.py` en la carpeta del usuario. Comando `/documentos` para subir, ver y borrar. El tipo de un campo de
archivo sale de su etiqueta por reglas (`transcript|certificado de notas|calificaciones` → `certificado_notas`,
`cover letter|carta` → `carta`, `portfolio|portafolio` → `portafolio`, `resume|cv|currículo|hoja de vida` →
`cv`) y, si ninguna aplica, por `clasificar_pregunta`. Un campo de carta obligatorio sin documento se llena
con un PDF generado de la carta redactada (tarea `carta` y `cv_pdf.py`). Uno opcional se deja vacío.

### 11. Modo ensayo y su límite en los portales declarados
El ensayo se detiene antes del **primer** paso que registra envío: `accion: enviar`, `envia: true` o un botón
`enviar` del bucle genérico. En Computrabajo, elempleo (normal) y Magneto, eso es el botón de postular de la
vacante. Ahí el ensayo comprueba la sesión, que la vacante sigue abierta y que el botón existe (lo que más se
rompe), pero no ve el formulario de después. En los formularios genéricos, el ensayo recorre todo. Estado
nuevo `ensayada` en `cola.E`, final, reportable por la extensión y reintentable con «Enviar de verdad».

### 12. Vigía
Tipo de trabajo nuevo `vigia`, solo para el navegador del dueño, a la hora `asistente.vigia.hora` (por
defecto 05:30). Elige por plataforma una vacante abierta reciente del índice que el dueño no tenga en la
cola, corre en ensayo y reporta al dueño. Un fallo no reparado pone la plataforma en ensayo
(`plataformas_en_ensayo` en la base, no en `config.yaml`) hasta `/plataformas <p> real`.

### 13. Métricas
`calcular_metricas_asistente` suma, por plataforma y por familia, los estados finales y los pasos
`reparacion`, `arbitro` y `respaldo:<motivo>` del historial. Mientras `familia_de` no exista, la familia es
la plataforma.

### 14. Niveles de IA como presets
`asistente.niveles_ia.{ahorro,normal,maximo}` define por nivel `max_arbitro`, `max_reparaciones`,
`clasificar_preguntas`, `modelo` (`ligero`, `configurado` o `maximo`), `requisitos_en_redactor`,
`ejemplos_estilo`, `doble_redaccion`, `revisor_final`, `carta_opcional` y `llamadas_estimadas` (para mostrar el
costo). Los valores de `asistente.motor_generico` son el techo: un nivel nunca los supera. El nivel del usuario
se guarda en sus preferencias y se copia a la postulación al encolar, para que un cambio de nivel no afecte lo
que ya está en curso. `ClienteIA` recibe el nivel efectivo: con `maximo` usa `modelo_maximo` y
`razonamiento_maximo` de la tarea si el proveedor los define, y si no, el modelo configurado.

*Alternativa descartada:* cuatro niveles (bajo, medio, alto, máx). Entre «alto» y «máx» no hay hoy una
diferencia que el usuario note, y más opciones confunden. Si se suma la visión (capturas), puede volver a
abrirse.

### 15. Revisor final y doble redacción
`revisar_respuestas` recibe las preguntas, las respuestas redactadas (con sus alternativas, si hubo doble
redacción), el idioma, los límites y los mismos datos del usuario que el redactor. Devuelve por respuesta
`ok`, `elegir` (índice de la alternativa), `corregir` (texto nuevo) o `preguntar` (con el dato dudoso).
Solo ve respuestas de origen `ia`: las de datos simples, consentimientos, opciones resueltas por datos y las
del usuario no se le envían. Un `corregir` pasa por `recortar_a_limite` y por la misma validación que el
redactor. Con «Revisar respuestas antes de enviar» encendido, el usuario ve el texto ya revisado.

### 16. Bajada de nivel por cuota
`CuotaAgotada` o `TopeAlcanzado` en una tarea con el nivel efectivo `maximo` reintenta la misma llamada con
`normal`, y si no alcanza, con `ahorro`. La bajada vale para el resto del día del usuario
(`nivel_bajado_hasta`, en las preferencias) y deja el paso `nivel_bajado` en el historial, que la card muestra.

## Risks / Trade-offs

- [Un clic mal clasificado envía antes de tiempo] → solo los botones `enviar` registran el envío. Un botón
  de clase dudosa pasa por el árbitro, y la extensión nunca pulsa uno `nunca`. Cada plataforma o familia
  nueva empieza en ensayo.
- [La IA se equivoca de botón] → índices validados, lista cerrada, tope de llamadas, y comprobación del
  resultado después de cada acción. Un error sin envío solo cuesta una reparación.
- [Cuota de IA gratis agotada] → reglas y recetas primero (0 llamadas en dominios conocidos), cadena de
  modelos de respaldo, `sin_ia` al respaldo y, si el dueño quiere, su clave solo para reparar.
- [Receta envenenada por una página rara] → solo se crea con `enviada` y señal explícita, por host, con
  selectores calculados sobre elementos reales, y se apaga con 2 fallos seguidos.
- [Datos personales en el resumen o en la evidencia] → el resumen nunca lee `value`, `checked` ni
  `files`. Hay pruebas que llenan un formulario con valores marcadores y verifican que no aparecen en
  `/pantalla`, `/reparar` ni en la evidencia.
- [El service worker MV3 se duerme en un bucle largo] → cada pantalla hace llamadas a la API y a
  `chrome.scripting`, que lo mantienen activo. El bucle guarda en `chrome.storage` la pantalla en curso y,
  si el worker se reinicia sin envío registrado, la postulación vuelve a la cola como hoy.
- [El respaldo genérico de un portal declarado hace algo inesperado] → solo antes del envío, con el mismo
  `paginaPermitida`, y se puede apagar con `respaldo_declarado: false`.

- [Máximo gasta mucha cuota] → techo de `motor_generico`, bajada de nivel por cuota y costo visible. El
  revisor solo ve respuestas redactadas por la IA, no todo el formulario.
- [El revisor «mejora» un dato hasta inventarlo] → solo corrige textos de origen `ia`, con la misma regla de
  no inventar del redactor, y ante la duda manda a la card. Hay pruebas con perfiles que no cumplen un
  requisito de la vacante.

## Migration Plan

1. Servidor primero, compatible con la extensión 1.1.x: `/formulario` sigue igual, y `/pantalla`,
   `/reparar`, las recetas y el estado `ensayada` son aditivos.
2. Extensión 1.2.0 con el bucle, publicada con `motor_generico.respaldo_declarado: false`.
3. Ensayo y vigía en los tres portales declarados, después `respaldo_declarado: true` y `version_minima: 1.2.0`.
4. Vuelta atrás: `respaldo_declarado: false` y `motor_generico.activo: false` dejan los flujos declarados como
   hoy, sin desinstalar nada.

## Open Questions

- La hora exacta del vigía y si debe saltarse los domingos (se ajusta en `config.yaml`).
- El umbral del 80 % de coincidencia de las firmas se afina con los datos de los primeros ensayos.
