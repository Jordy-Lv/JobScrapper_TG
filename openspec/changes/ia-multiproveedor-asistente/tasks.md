# Tasks

Dificultad de cada grupo: 🟡 media · 🔴 pesada · 👤 del dueño. Los grupos 2, 3 y 4 son 🔴: conviene sesión nueva antes de cada uno.

## 1. Configuración y catálogo de proveedores 🟡

- [x] 1.1 En `config.py`, reemplazar `AsistenteGemini` por `AsistenteIA` con `proveedores: dict[str, ProveedorIA]` (protocolo `gemini|openai|anthropic`, `nombre`, `base_url`, `url_clave`, `pasos_clave`, `gratuito`, `acepta_pdf`, `timeout_s`, `tareas`); validar que cada proveedor define todas las tareas y que `base_url` es https. Verificar con pruebas en `tests/test_config.py` (proveedor completo, tarea faltante, protocolo desconocido, `base_url` http).
- [x] 1.2 Migrar el bloque `asistente.gemini` de `config.yaml` a `asistente.ia.proveedores.gemini` sin cambiar sus modelos, y agregar las entradas de Groq, OpenRouter, OpenAI, Anthropic y DeepSeek con modelos provisionales marcados "sin verificar" hasta la tarea 7.2. Verificar que `uv run buscador.py` carga la configuración y que `tests/test_config.py` sigue en verde.

## 2. Cliente de IA genérico y adaptadores 🔴

- [x] 2.1 Separar `asistente/gemini.py`: extraer a un módulo `ia/` el cliente genérico `ClienteIA` (topes, `ia_uso`, delimitación de datos, reintento por JSON inválido, cadena de modelos) y el contrato del adaptador; renombrar `ClaveGeminiInvalida`→`ClaveInvalida` y `ClienteGemini`→`ClienteIA` en todos los consumidores. Verificar con `tests/test_asistente_gemini.py` migrado a la nueva estructura, sin pérdida de casos.
- [x] 2.2 Adaptador `gemini` con el comportamiento actual (esquema OpenAPI, `thinkingConfig`, PDF en línea, `retryDelay`). Verificar que las pruebas existentes de Gemini pasan sin cambios de expectativas.
- [x] 2.3 Adaptador `openai` (chat completions: `response_format` json_schema con respaldo a `json_object`, validación de clave con la lista de modelos, 401/403 → clave inválida, 429 → cuota con `Retry-After`, 5xx → saturado). Verificar con pruebas `respx` de éxito, JSON inválido, 400 por `response_format`, 429, 503 y clave inválida.
- [x] 2.4 Adaptador `anthropic` (mensajes con herramienta forzada, PDF como documento en línea, validación de clave, mismos mapeos de error). Verificar con pruebas `respx` equivalentes a 2.3 más el caso con PDF.
- [x] 2.5 Prueba transversal: la misma tarea con los tres adaptadores simulados nunca envía documento, teléfono, correo ni dirección y trata la vacante con instrucción incrustada como datos. Verificar que pasa para los tres protocolos.

## 3. Datos, cifrado y núcleo 🔴

- [ ] 3.1 Migración de `asistente.db` (`ESQUEMA_VERSION` + 1): renombrar `gemini_clave/ult4/valida` a `ia_clave/ult4/valida`, agregar `ia_proveedor` y fijar `'gemini'` donde hay clave. Verificar con una prueba que crea una base con el esquema anterior, migra y comprueba que la clave descifra igual y que los usuarios sin clave quedan sin proveedor.
- [ ] 3.2 Actualizar `cifrado.py` (`COLUMNAS_CIFRADAS`, textos que nombran a Gemini) y `cli.py` (aviso de clave maestra). Verificar con `tests/test_asistente_cifrado.py` que la rotación recifra `ia_clave` de usuarios con distintos proveedores.
- [ ] 3.3 En `nucleo.py`, reemplazar `clave_gemini/guardar_clave_gemini/marcar_clave_invalida` por versiones con proveedor, elegir el adaptador por proveedor del usuario y tratar un proveedor retirado del catálogo como clave no disponible con aviso. Verificar con pruebas en `tests/test_asistente_nucleo.py` (usuario de cada protocolo, proveedor retirado, clave inválida durante `preparar` y `resolver_formulario`).
- [ ] 3.4 Adaptar `cv_lectura.py`, `cv_adaptado.py`, `respuestas.py` y `afinidad.py` al cliente nuevo y aplicar `acepta_pdf`: sin PDF el escaneado va al cuestionario guiado sin confirmar el envío. Verificar con `tests/test_asistente_cv_lectura.py` (escaneado con y sin `acepta_pdf`) y los demás tests del asistente en verde.

## 4. Conversación, textos y política 🔴

- [ ] 4.1 Paso 2 del alta: sustituir `t.PEDIR_CLAVE` por la elección de proveedor con botones (gratuitos marcados, "No tengo clave por ahora"), los pasos del proveedor elegido tomados del catálogo y `_recibir_clave` validando contra ese proveedor, con los mensajes de clave inválida y de proveedor sin respuesta nombrando al proveedor. Verificar con `tests/test_asistente_bot.py`: elegir proveedor, clave válida, inválida, proveedor sin respuesta y omitir.
- [ ] 4.2 `/clave`: mostrar proveedor y terminación, permitir cambiar de proveedor o borrar, y hacer que los avisos de clave inválida y de cuota agotada nombren al proveedor y solo digan "gratuita" si el catálogo lo indica. Verificar con pruebas del bot (cambio de Gemini a otro proveedor, borrado, aviso de cuota de un proveedor de pago).
- [ ] 4.3 Neutralizar los demás textos que nombran a Gemini (`textos.py`: ayuda, `CV_ESCANEADO` con el nombre del proveedor; `conversacion.py`: "Como no tengo clave…"). Verificar con `grep -ri gemini buscador_vacantes/asistente/textos.py buscador_vacantes/asistente/conversacion.py` sin ocurrencias fuera del catálogo y con las pruebas del bot en verde.
- [ ] 4.4 Reescribir el punto 3 de la política de `config.yaml` en términos del proveedor elegido y subir `politica.version` a 2. Verificar con una prueba de que un usuario activo con versión 1 recibe la solicitud de aceptación y, al aceptar, retoma la vacante pendiente.

## 5. Documentación y despliegue 🟢

- [ ] 5.1 Actualizar `docs/guia-usuario.md` (elegir proveedor, qué cuesta cada uno, cómo cambiarlo), `deploy/INSTALAR.md` (respaldar `asistente.db` antes de actualizar, nueva aceptación de política, cómo agregar un proveedor al catálogo) y `.env.example`. Verificar leyendo que ningún documento promete "clave gratuita de Gemini" como única opción.

## 6. Verificación integral 🟡

- [ ] 6.1 Ejecutar `uv run pytest` y `uv run ruff check .` completos y la prueba de extremo a extremo del asistente simulado (alta con un proveedor distinto de Gemini → CV → postulación con CV adaptado). Verificar con todo en verde.

## 7. Pruebas reales y despliegue 👤

- [ ] 7.1 Dueño: respaldar `asistente.db` en el Fedora, actualizar el servicio con `deploy/INSTALAR.md` y comprobar que los usuarios del piloto conservan su clave de Gemini y reciben la política v2.
- [ ] 7.2 Dueño: con una clave real de cada proveedor del catálogo inicial, correr la prueba de humo (validar clave, leer un CV de prueba, adaptar y redactar) y confirmar o corregir en `config.yaml` los modelos, `acepta_pdf` y `gratuito`; los proveedores que no pasen la prueba se quitan del catálogo por defecto.

## 8. Cierre

- [ ] 8.1 Archivar primero `asistente-postulacion-telegram` y después este change con `/opsx:archive`. Verificar con `openspec list --specs` que `ia-usuario-multiproveedor` existe.
- [ ] 8.2 Retirar `ia-usuario-gemini` de `openspec/specs/` (reemplazada) y ajustar los textos que nombran a Gemini en `usuarios-asistente` y `cv-adaptado`. Verificar con `openspec validate --specs` y `grep -ri gemini openspec/specs`.
