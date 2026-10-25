## Why

Hoy cada portal tiene un flujo declarado a mano (`assets/asistente/selectores/*.json`). Si el portal cambia
un botón o muestra un paso nuevo, la postulación termina en `formulario_desconocido` y alguien tiene que
corregir los selectores. Así pasó con el cuestionario adicional de elempleo el 2026-10-17. Además, el
dueño decidió (2026-10-21) postular también en LinkedIn, cuyas vacantes llevan a ATS muy distintos
(Greenhouse, Ashby, Typeform, Pandapé, sitios propios…), imposibles de declarar uno por uno. El
reconocimiento de esos destinos (`docs/asistente/portales.md`, sección «LinkedIn») mostró que casi todos
usan un marcado accesible que permite leerlos de forma genérica. El dueño pidió un motor que **entienda
los formularios solo**, use la IA que cada usuario configuró **solo cuando la necesita**, **se repare
solo** cuando algo falla antes del envío y valga **para todas las plataformas**.

## What Changes

- **Bucle genérico de postulación** en la extensión: lee la pantalla (formulario, página intermedia, éxito,
  error o barrera), extrae el esquema de los campos, incluidos los controles ARIA (combobox, listas,
  radios, casillas) y los formularios sin `<form>` o dentro de iframes, llena y comprueba cada campo,
  elige el botón de avanzar o enviar y detecta el resultado. Repite hasta terminar, con topes de
  pantallas y de tiempo.
- **Barreras que detienen sin enviar**: contraseña, crear cuenta o iniciar sesión, OAuth como único
  camino, desafío de captcha **visible** (un captcha invisible ya no cuenta como captcha) y código de
  verificación. Nunca se llenan campos ocultos, trampas ni contraseñas.
- **Resolvedor ampliado** en el servidor: `autocomplete`, tokens de `name`/`id`, banco sembrado en inglés
  y portugués, campos nuevos del catálogo (nombre de pila, apellido, país, LinkedIn, autorización para
  trabajar, promedio, fuente de la vacante) y respuestas **en el idioma del formulario**.
- **Dos tareas de IA nuevas**, con la clave del usuario: `entender_pagina` (árbitro cuando las reglas dudan)
  y `reparar_flujo` (corrección cuando un paso falla antes del envío). La IA solo responde índices de la
  lista que le pasa el motor y acciones de una lista cerrada, validadas con pydantic.
- **Autorreparación**: antes de pulsar enviar, hasta 2 reparaciones por postulación. Después de pulsar
  enviar, nunca se reintenta solo. En Computrabajo, Magneto y elempleo, un paso declarado que falla antes
  del envío pasa al bucle genérico en vez de terminar en `formulario_desconocido`.
- **Nivel de uso de IA por usuario** (Ahorro, Normal por defecto, Máximo), elegido por Telegram y en el popup.
  Decide cuánto árbitro, reparación y modelo usa la postulación, sin tocar las reglas de seguridad. Máximo
  suma un modelo completo, respuestas alineadas a los requisitos de la vacante, el estilo del usuario, doble
  redacción de las respuestas largas, un **revisor final** (tarea `revisar_respuestas`) y la carta opcional en
  PDF. Si se agota la cuota, el nivel baja en vez de fallar, y el costo de cada nivel se muestra.
- **Funcionamiento sin IA** como contrato: reglas, recetas y datos del usuario postulan solos; lo abierto va a
  la card, y lo que necesitaría IA va al respaldo con `sin_ia`, sin enviar nada.
- **Recetas por dominio y parches candidatos**: lo que funcionó (mapeo de campos, botones y señal de éxito,
  sin valores) se guarda y se comparte. Las correcciones de los flujos declarados se prueban como
  candidatas y pasan a firmes con un éxito. Los dominios que piden cuenta se recuerdan como barrera.
- **Esquema anticipado (mecanismo)**: si el trabajo llega con el esquema del formulario ya leído, el servidor
  resuelve todo antes de abrir la pestaña y lo que falte se pregunta en la misma card, antes de encolar.
  Los lectores de cada ATS (Greenhouse, Ashby, Lever, Typeform) llegan con `postular-linkedin`.
- **Perfil de postulación ampliado y documentos extra** por Telegram (autorización para trabajar, salario en
  COP y USD, promedio, enlaces y PDF como el certificado de notas), cifrados y adjuntados solo cuando un
  formulario los pide.
- **Modo ensayo** (llenar todo sin enviar, estado nuevo `ensayada`), por plataforma y por usuario, y un
  **vigía diario** que recorre en ensayo una vacante de cada plataforma en el navegador del dueño.
- **Banco de pruebas** con páginas reales recortadas y Playwright contra un envío falso, y **métricas** por
  plataforma y familia en el resumen del dueño.
- La extensión sube de versión (1.2.0) y `version_minima` sube con ella. El permiso amplio para páginas
  externas **no** va aquí: llega con `postular-linkedin`.

## Capabilities

### New Capabilities
- `motor-generico-postulacion`: bucle genérico de la extensión (lectura de pantalla, esquema con
  controles ARIA e iframes, llenado comprobado, botones, resultado, barreras y topes) y su uso como
  respaldo de los flujos declarados.
- `autorreparacion-postulacion`: árbitro y reparación con la IA del usuario, límites de la IA, reintentos
  antes del envío, recetas por dominio, parches candidatos y dominios barrera.
- `perfil-postulacion-ampliado`: datos de postulación que piden los ATS (autorización para trabajar,
  salario en COP y USD, promedio, enlaces), documentos extra cifrados y el esquema anticipado que resuelve
  las preguntas antes de encolar.
- `ensayo-vigia-postulacion`: modo ensayo, vigía diario, banco de pruebas con páginas reales y métricas.
- `nivel-ia-postulacion`: niveles Ahorro, Normal y Máximo por usuario, calidad del nivel Máximo con su
  revisor final, bajada de nivel por cuota, costo visible y funcionamiento sin IA.

### Modified Capabilities
- `preguntas-encuesta-asistente`: el redactor responde en el idioma del formulario (hoy siempre en
  español) y los datos simples también se resuelven por `autocomplete` y por el nombre del campo.

## Impact

- **Extensión**: `extension/motor.js` (lectura de pantalla, controles ARIA, botones, resultado, barreras,
  resumen sin valores para la IA), `extension/servicio.js` (bucle, reparación, iframes con `allFrames`,
  ensayo, vigía), `extension/manifest.json` (versión 1.2.0).
- **Servidor**: `asistente/respuestas.py` y `asistente/campos.py` (resolvedor, catálogo, idioma),
  `asistente/api.py` (campos nuevos en `Campo`, endpoints `/pantalla` y `/reparar`, recetas en el trabajo,
  resultado `ensayada`), `asistente/cola.py` (estado `ensayada`), módulos nuevos `asistente/recetas.py` y
  `asistente/pantalla.py`, `asistente/ia` (tareas nuevas en
  `cfg.NombreTarea`), la conversación de Telegram (perfil ampliado y documentos) y el resumen del dueño.
- **Datos**: tablas nuevas en la base del asistente (`recetas`, `parches_flujo`, `dominios_barrera`,
  `documentos_usuario`); el banco de preguntas crece con sinónimos en inglés y portugués.
- **Configuración**: `config.yaml` → las tareas `entender_pagina`, `reparar_flujo` y `revisar_respuestas` en los seis proveedores
  (con `modelo_maximo` por tarea), la sección `asistente.niveles_ia`
  de IA, y las secciones nuevas `asistente.motor_generico`, `asistente.autorreparacion` (con
  `clave_duenio: false`), `asistente.ensayo` y `asistente.vigia`.
- **Pruebas**: fixtures recortados por familia y portal en `tests/fixtures/formularios/`, pruebas de
  Playwright de la extensión y pruebas del servidor con `respx`.
- **Autorización de datos**: los documentos extra son datos nuevos; la política sube de versión.
- Sin cambios en el radar ni en `vacantes.db`.
