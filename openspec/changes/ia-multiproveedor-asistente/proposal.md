# Proposal

## Why

El asistente de postulación solo funciona con Gemini: el paso 2 del alta ("Tu clave gratuita de
Gemini"), el cliente de IA, la base de datos (`gemini_clave`), los mensajes y la política de
privacidad están atados a Google. Quien ya tiene una clave de OpenAI, Anthropic, Groq u otro
proveedor no puede usarla, y si Google cambia su oferta gratuita (como ya pasó con los
`gemini-2.5-*`) el servicio queda sin IA para todos. Cada usuario debe poder traer la clave del
proveedor que prefiera.

## What Changes

- El paso 2 del alta y el comando `/clave` dejan de asumir Gemini: el usuario **elige proveedor**
  entre un catálogo y recibe las instrucciones para obtener la clave de ese proveedor.
- Nuevo catálogo de proveedores en `config.yaml` (nombre, protocolo, URL base, enlace y pasos para
  obtener la clave, si tiene plan gratuito, si acepta PDF, y modelos por tarea). Un proveedor con
  API compatible con OpenAI se agrega **solo con configuración**, sin tocar código.
- Soporte de tres protocolos: Gemini (el actual), compatible con OpenAI (cubre OpenAI, Groq,
  OpenRouter, DeepSeek, Mistral, Together, etc.) y Anthropic.
- El cliente `ClienteGemini` se generaliza a un cliente de IA único (topes, uso, reintentos,
  cadena de modelos de respaldo, validación con esquema) con un adaptador por protocolo.
- La clave se guarda cifrada junto con el proveedor elegido; cada usuario tiene un único proveedor
  activo y puede cambiarlo o borrarlo con `/clave`.
- Textos del bot, aviso de cuota y política de privacidad pasan a hablar del "proveedor de IA" del
  usuario (con su nombre), sin asumir que el plan es gratuito. **BREAKING**: sube la versión de la
  política y los usuarios activos deben aceptarla de nuevo, porque cambia quién puede recibir sus
  datos.
- **BREAKING**: migración del esquema de `asistente.db` (`gemini_*` → `ia_proveedor`, `ia_clave`,
  `ia_ult4`, `ia_valida`) y del bloque `asistente.gemini` de `config.yaml`. Los usuarios existentes
  quedan con proveedor `gemini` y su clave intacta.
- Si el proveedor del usuario no acepta PDF, el CV escaneado se resuelve con el cuestionario
  guiado en vez de enviar el archivo.

## Capabilities

### New Capabilities
- `ia-usuario-multiproveedor`: la IA del asistente con la clave propia del usuario en el proveedor
  que elija (catálogo configurable, protocolos soportados, elección y cambio de proveedor,
  capacidades por proveedor, mensajes y política neutros, migración desde Gemini). Reemplaza a
  `ia-usuario-gemini` del change `asistente-postulacion-telegram`, conservando todas sus garantías
  (datos que nunca se envían, contenido externo como datos, topes, cuota agotada).

### Modified Capabilities
<!-- Ninguna en openspec/specs/: las specs del asistente aún viven en el change
     asistente-postulacion-telegram (sin archivar). Ver "Orden de archivo" en design.md. -->

## Impact

- Código: `buscador_vacantes/asistente/gemini.py` (se divide en cliente genérico + adaptadores),
  `nucleo.py`, `conversacion.py`, `textos.py`, `datos.py` (migración), `cifrado.py` (columna
  cifrada), `cv_lectura.py`, `cv_adaptado.py`, `respuestas.py`, `afinidad.py`, `servicio.py`,
  `cli.py` y `config.py` (modelos de configuración).
- Configuración: `config.yaml` (bloque `asistente.gemini` → `asistente.ia` con `proveedores`; texto
  y versión de la política), `.env.example` y `deploy/INSTALAR.md`.
- Documentación: `docs/guia-usuario.md`.
- Datos: migración de `asistente.db` en el Fedora (usuarios del piloto) y nueva aceptación de
  política.
- Sin dependencias nuevas: todo va por `httpx`.
- No toca el buscador ni el cliente de DeepSeek del propio buscador (`ia_cliente.py`), que sigue con
  la clave del dueño.
