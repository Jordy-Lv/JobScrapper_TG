# Design

## Context

Motivación y alcance: ver `proposal.md`. Estado actual observado en el código:

- `asistente/gemini.py` (315 líneas) mezcla dos cosas: lo genérico (topes diarios por `ia_uso`, delimitación de datos, reintentos por JSON inválido, cadena de modelos de respaldo, registro de uso) y lo propio de Gemini (endpoint `models/{m}:generateContent`, cabecera `x-goog-api-key`, `responseSchema` en subconjunto OpenAPI, `thinkingConfig`, `inlineData` para PDF, lectura de `retryDelay` en 429, `API_KEY_INVALID`).
- Los consumidores (`nucleo.py`, `conversacion.py`, `afinidad.py`, `respuestas.py`, `cv_lectura.py`, `cv_adaptado.py`) llaman a `ClienteGemini.generar(tarea, clave, usuario_id, instruccion, partes, esquema)` y capturan `ErrorIA`, `ClaveGeminiInvalida`, `CuotaAgotada`, `Saturado`, `RequiereConfirmacion`.
- La BD guarda `usuarios.gemini_clave` (Fernet), `gemini_ult4`, `gemini_valida`; `cifrado.py` lista `gemini_clave` en `COLUMNAS_CIFRADAS` para la rotación de la clave maestra; `datos.py` migra con `ESQUEMA_VERSION` y `_actualizar_desde`.
- `config.yaml` tiene `asistente.gemini` (`base_url`, `timeout_s`, `tareas` con modelo, temperatura, `max_tokens`, `pensamiento`, `respaldo`) y el texto de la política (versión 1) que nombra a Gemini.
- El paso 2 del alta es `t.PEDIR_CLAVE` + `_recibir_clave` en `conversacion.py`; `/clave` es `_c_clave`.
- `ia_cliente.py` (DeepSeek del buscador) es independiente y no se toca.

## Goals / Non-Goals

**Goals:**
- Que añadir un proveedor con API compatible con OpenAI sea solo configuración.
- Que Gemini, OpenAI-compatible y Anthropic compartan topes, uso, reintentos, respaldo y validación, para que las garantías de privacidad no dependan del proveedor.
- Migrar a los usuarios del piloto sin que repitan nada salvo aceptar la política nueva.

**Non-Goals:**
- Que el usuario escriba una URL o modelo propios (riesgo de SSRF y de salidas imprevisibles); el catálogo lo define el dueño.
- Que el usuario tenga varios proveedores a la vez o un orden de respaldo entre proveedores.
- Modelos locales (Ollama) o autenticación distinta de una clave de API.
- Cambiar los usos permitidos de la IA, los topes o los validadores de veracidad.
- Tocar el cliente de DeepSeek del buscador.

## Decisions

### D1. Tres protocolos, proveedores como datos
Los **protocolos** son código (`gemini`, `openai`, `anthropic`); los **proveedores** son entradas del catálogo `asistente.ia.proveedores` en `config.yaml`, cada una con `protocolo`, `nombre`, `base_url`, `url_clave`, `pasos_clave` (texto para el bot), `gratuito` (bool), `acepta_pdf` (bool), `timeout_s` y `tareas`. Catálogo inicial propuesto: Gemini, Groq y OpenRouter (con plan gratuito) y OpenAI, Anthropic y DeepSeek (de pago).

*Alternativa descartada:* una clase por proveedor. Multiplica código casi idéntico, porque la mayoría habla el protocolo de OpenAI.
*Alternativa descartada:* una librería multiproveedor (LiteLLM, etc.). Agrega una dependencia grande y opaca; el proyecto ya usa `httpx` directo y tres adaptadores son ~100 líneas cada uno.

### D2. Cliente genérico + adaptadores
`ClienteIA` conserva lo genérico de `ClienteGemini` (topes, `ia_uso`, delimitación de datos, reintento por JSON inválido, cadena de modelos). Cada adaptador implementa un contrato mínimo: `validar_clave(clave)`, `generar(modelo, clave, instruccion, partes, esquema, ajustes) -> (texto_json, tokens_in, tokens_out)`, y traduce los fallos HTTP a las excepciones comunes (`ClaveInvalida`, `CuotaAgotada`, `Saturado`, `ModeloNoDisponible`, `ErrorIA`). El cliente elige el adaptador según el proveedor del usuario en cada llamada; no hay estado por usuario en el cliente.

Los nombres cambian: `ClienteGemini`→`ClienteIA`, `ClaveGeminiInvalida`→`ClaveInvalida`. Se renombra todo de una vez (el proyecto no tiene consumidores externos) en vez de dejar alias.

### D3. Salida estructurada por protocolo, validada siempre en el cliente
- **gemini:** `responseSchema` como hoy.
- **openai:** `response_format: json_schema` y, si el proveedor lo rechaza con 400, un segundo intento con `json_object` más el esquema descrito en la instrucción. Los proveedores compatibles no soportan el modo estricto por igual.
- **anthropic:** el esquema va como herramienta única forzada (`tool_choice`) y se lee el `input` de la herramienta.

En los tres casos el resultado se valida con pydantic, que es la garantía real; el modo del proveedor solo mejora la tasa de acierto. Se recuerda en la instrucción que el JSON es la única salida.

### D4. Esquema de BD: `ia_proveedor` + `ia_clave` + `ia_ult4` + `ia_valida`
Se renombran las columnas de `usuarios` y se añade `ia_proveedor` (id del catálogo). Migración con `ESQUEMA_VERSION` + 1 en `_actualizar_desde`: `ALTER TABLE … RENAME COLUMN` (SQLite ≥ 3.25) y `ia_proveedor = 'gemini'` donde `ia_clave IS NOT NULL`. `COLUMNAS_CIFRADAS` pasa a `ia_clave`. Si el id guardado ya no existe en el catálogo (el dueño lo quitó), la clave se trata como no disponible y se avisa al usuario, igual que una clave inválida.

*Alternativa descartada:* tabla aparte de claves por proveedor. Permitiría varios proveedores a la vez, pero es un non-goal y complica `/clave`, el borrado y la rotación.

### D5. Elección en el chat con botones
Paso 2: mensaje corto "Elige tu proveedor de IA" con un botón por proveedor (los gratuitos marcados) más "No tengo clave por ahora". Al tocar uno, se muestran `pasos_clave` y `url_clave` de ese proveedor y se espera la clave (`_esperar({"tipo": "clave", "proveedor": id})`). Los botones usan el `cb("clave", …)` existente. El texto `PEDIR_CLAVE` fijo se reemplaza por una plantilla armada con el catálogo; los pasos reales viven en `config.yaml`, no en `textos.py`. `/clave` reutiliza el mismo flujo y muestra el proveedor actual.

*Alternativa descartada:* detectar el proveedor por el prefijo de la clave (`sk-ant-`, `AIza`, `gsk_`). Es frágil (OpenAI, DeepSeek y OpenRouter comparten `sk-`) y falla en silencio; la elección explícita es más clara.

### D6. Capacidad de PDF por proveedor
`acepta_pdf` en el catálogo. `cv_lectura` ya separa "PDF con texto" (extracción local, sin PDF al proveedor) de "escaneado" (`RequiereConfirmacion`); solo cambia el escaneado: si `acepta_pdf` es falso se salta la confirmación y se va al cuestionario guiado (`_perfil_manual`). Gemini y Anthropic aceptan PDF en línea; los compatibles con OpenAI se marcan falsos por defecto (soporte desigual) y el dueño puede activarlo si verifica el suyo.

### D7. Respaldo de modelos y cuotas por proveedor
La cadena `modelo` + `respaldo` pasa a ser por proveedor y tarea, porque la cuota y la disponibilidad son por proveedor. El tope diario del asistente (`ia_usuario_dia`) sigue contando llamadas exitosas en `ia_uso` sin distinguir proveedor. Los mensajes de cuota usan `nombre` del proveedor y solo dicen "gratuita" si `gratuito` es verdadero. `pensamiento` queda como ajuste opcional que solo aplica el adaptador de Gemini y se ignora en los demás.

### D8. Política y re-aceptación
El punto 3 de la política se reescribe en términos de "el proveedor de IA que tú elijas", y se avisa que el plan gratuito de algunos proveedores puede usar el contenido para entrenar. Sube `politica.version` a 2; el mecanismo existente de re-aceptación (`politica_version`) obliga a los usuarios activos a aceptar de nuevo. Se mantiene la lista de lo que nunca se envía.

### D9. Orden de archivo
Las specs del asistente aún no están en `openspec/specs/` (el change `asistente-postulacion-telegram` está en curso), por eso este change declara una capability nueva en vez de MODIFIED. Al archivar: primero `asistente-postulacion-telegram`; después este change, y en ese momento se retira `ia-usuario-gemini` de `openspec/specs/` (la nueva la reemplaza) y se ajustan los textos que nombran a Gemini en `usuarios-asistente` y `cv-adaptado` (tarea 8.2). Si este change se implementa antes de archivar el otro, no hay conflicto de código: las specs son independientes.

## Risks / Trade-offs

- **Los modelos y endpoints de cada proveedor cambian (ya pasó con Gemini 2.5)** → Los modelos viven en `config.yaml`; se verifican contra la API real antes de dejarlos como valores por defecto (tarea 7.2, del dueño, necesita claves) y la cadena de respaldo cubre retiros.
- **Calidad desigual entre modelos y proveedores (JSON, español, veracidad)** → Todo pasa por el esquema pydantic y los validadores de veracidad existentes; hay pruebas con respuestas simuladas por protocolo y una prueba de humo real por proveedor del catálogo inicial. Un proveedor sin prueba de humo no entra al catálogo por defecto.
- **Más proveedores, más sitios que reciben datos personales** → Mismo enmascarado para todos, política v2 con aceptación explícita y catálogo cerrado definido por el dueño (sin URL del usuario).
- **Proveedores de pago generan costo al usuario sin que lo note** → El bot lo indica al elegir; el tope diario de llamadas se mantiene para todos.
- **Migración de columnas en producción (Fedora)** → La migración es una versión de esquema con prueba sobre una base creada con el esquema anterior; se respalda `asistente.db` antes de actualizar (paso en `deploy/INSTALAR.md`). Revertir requiere restaurar ese respaldo, porque el código nuevo no es compatible con el esquema viejo.
- **`openai` compatible no es un estándar exacto** (parámetros como `max_tokens` vs `max_completion_tokens`, `response_format`) → El adaptador usa el subconjunto común y el fallback de D3; cada particularidad que aparezca en la prueba real se resuelve con una opción del catálogo, no con ramas por proveedor.
