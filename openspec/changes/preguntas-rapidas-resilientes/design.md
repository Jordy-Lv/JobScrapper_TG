## Context

Todos los portales pasan por `Nucleo.resolver_formulario` (`nucleo.py`): el formulario clásico de la extensión (`/formulario`), el bucle del motor genérico (`/pantalla`) y la anticipación de esquemas de LinkedIn. Esa función resuelve cada pregunta con `resolver` (aprendidas → banco → perfil → clasificación por IA), redacta las abiertas en una sola llamada (`_redactar`) y, si alguna obligatoria queda sin respuesta, crea un pendiente (`_crear_pendientes`) y la postulación pasa a `esperando_usuario`.

Hoy:
- Una falla de IA se trata igual que no tener IA: `redactar_formulario` devuelve `None` en ambos casos y `resolver` captura `ErrorIA` y devuelve `falta=True`. El cliente (`ia/cliente.py`) ya reintenta 3 s y 8 s y prueba otro modelo; si Gemini sigue saturado, se rinde en segundos.
- La card pone botones solo desde `pendientes_usuario.opciones_json`, que sale de `Pregunta.opciones` (las del portal) o de las sugerencias del redactor. Un campo de texto con una pregunta de sí o no queda sin botones (`tarjeta_postulacion._botones_pregunta`), y `conversacion._texto_pendiente` solo acepta texto si no hay opciones o se tocó «Escribir yo».
- `responder_pendiente` ya guarda la respuesta con `recordar` (por el texto exacto de la pregunta) y, si el pendiente trae un `campo` guardable, también en el cuestionario. El aval no tiene campo, así que solo se recuerda con la redacción exacta.
- La extensión no tiene tope de espera para `/formulario`, y `con_latido` (`api.py`) ya manda latidos cada 30 s mientras el servidor resuelve.

Ver `proposal.md` para el motivo.

## Goals / Non-Goals

**Goals:**
- Que una falla temporal de la IA no convierta preguntas respondibles en preguntas al usuario.
- Que cualquier pendiente de sí o no tenga botones, sin importar el portal.
- Que el aval se pregunte una sola vez y se reutilice con cualquier redacción.

**Non-Goals:**
- Un estado de cola «esperando a la IA» o reintentos de horas: el reintento es dentro de la misma pasada, de minutos.
- Cambios en la extensión, los selectores o el esquema de la base de datos.
- Redactar el «Sí» como frase completa: el texto del botón se envía tal cual.

## Decisions

**1. Reintentar dentro de `resolver_formulario`, no en la cola.** Se envuelve la resolución en un bucle con las esperas de `asistente.formulario_ia.esperas_s` (por defecto `[30, 60, 120]`, unos 3,5 min además de los reintentos del cliente, que cubren la saturación observada de 3 min). Mientras espera, `con_latido` ya mantiene vivo al navegador, así que no hace falta tocar la extensión ni la cola. Alternativa descartada: un estado nuevo en la cola con reintento posterior; exige cambios en la extensión, la card en cola y el vigilante para un caso que dura minutos.

**2. Qué cuenta como falla temporal.** `Contexto` gana `ia_fallo: bool`. Se enciende cuando `resolver` (clasificación) o `_redactar` reciben un `ErrorIA` que no es `ClaveInvalida`, `CuotaAgotada`, `TopeAlcanzado` ni `ModeloNoDisponible` (es decir, `Saturado` o sin contacto). `redactar_formulario` sigue devolviendo `None` por compatibilidad, y el contexto distingue el motivo. Con `ia_fallo` y preguntas obligatorias sin resolver, se espera la siguiente pausa y se vuelve a resolver solo lo que falló; lo ya resuelto (banco, aprendidas, opciones) no se repite porque el bucle conserva `resueltas` y reintenta solo `por_redactar` y las preguntas por clasificar.

**3. Aviso en la card.** Al agotar los reintentos se registra el paso `ia_no_respondio` en `postulacion_pasos` (mismo patrón que `nivel_bajado`) y la card lo lee para agregar una línea a la pregunta. No hay columna nueva.

**4. Detector de sí/no como función pura.** `es_pregunta_si_no(texto)` en `respuestas.py`: la pregunta normalizada empieza por un verbo de sí/no («cuentas con», «tienes», «cuenta con», «posees», «dispones», «estas», «puedes», «has», «eres», «aceptas», «tienes disponibilidad», «te encuentras», «cuentas», «habla», «conoces») y no contiene interrogativos de dato abierto («cuanto», «cuantos», «cual», «cuales», «que», «por que», «como», «donde», «cuando», «describe», «explica», «menciona»). Es conservadora: ante la duda, pide escribir como hoy. Alternativa descartada: preguntarle a la IA si es de sí/no; falla justo cuando la IA está caída, que es el caso a cubrir.

**5. Tipo de pendiente `si_no`.** `_crear_pendientes` guarda `opciones_json = ["Sí", "No"]` y `tipo = "si_no"` cuando la pregunta no trae opciones y `es_pregunta_si_no` es verdadera; en un pendiente de `dato` sin sugerencias solo agrega las opciones y conserva `dato`. La card trata `si_no` como `dato` en botones («Sí», «No», «✍️ Escribir yo») pero sin «Prefiero no decirlo», porque es una pregunta del portal. `_texto_pendiente` acepta texto escrito tras «Escribir yo» igual que en `dato`. El callback `pend` ya resuelve el índice contra `opciones_json`. La pregunta sin card (`pid is None`) usa las mismas opciones. Alternativa descartada: columna nueva o cambiar `Pregunta.opciones` en el esquema leído: forzaría a la extensión a marcar un campo de texto con opciones que no tiene.

**6. El aval como campo del catálogo.** `aval_institucion` en `CAMPOS` («si cuenta con el aval de su institución educativa para iniciar prácticas (sí/no)»), con 6 a 8 formulaciones sembradas en `banco_preguntas.yaml`. Con eso: `es_guardable` lo vuelve guardable, `responder_pendiente` ya lo escribe en el cuestionario, `DatosUsuario.valor` lo lee por la rama directa, `elegir_opcion` mapea «Sí»/«No» a las opciones del portal y la clasificación por IA puede encajar formulaciones nuevas en el campo (`clasificar_pregunta` recibe el catálogo). El campo no se agrega al cuestionario del alta (lo evalúa `preguntas-frecuentes-onboarding`).

**7. Configuración.** Las esperas van en `config.yaml` y se validan en `buscador_vacantes/comun/config.py` (lista de segundos, vacía para desactivar). Las pruebas la fijan en `[0, 0]` o con un reloj falso.

## Risks / Trade-offs

- [El detector acierta una pregunta que en realidad pedía texto, y el usuario recibe botones donde quería escribir] → «✍️ Escribir yo» siempre está; la lista de interrogativos es conservadora y se prueba con preguntas reales de los portales.
- [Una pasada que espera 3,5 min retrasa la cola de ese usuario] → solo ocurre con la IA caída, el usuario ya tiene una postulación en curso y la alternativa era preguntarle; el tope es configurable.
- [La anticipación de esquemas de LinkedIn corre sin `con_latido`] → espera dentro del toque del usuario, no del navegador; se verifica en la prueba que no deja la postulación como caída.
- [El texto «Sí» enviado a un campo de texto con límite o formato propio] → un campo de texto acepta «Sí»; los campos numéricos o con opciones no pasan por este camino.
- [El aval guardado queda viejo (cambia de institución)] → el usuario puede corregirlo en «Corregir y recordar» como cualquier dato aprendido.

## Migration Plan

Sin migración de datos. Despliegue: `git pull --ff-only` en el servidor y reiniciar `buscador-asistente`; el banco sembrado se carga al arrancar (`sembrar_banco` agrega las preguntas nuevas). Vuelta atrás: volver al commit anterior; los pendientes `si_no` ya creados se muestran con los botones «Sí» y «No» y sin «✍️ Escribir yo».
