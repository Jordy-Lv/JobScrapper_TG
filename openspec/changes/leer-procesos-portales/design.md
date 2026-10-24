## Context

- Ya funciona un patrón parecido. `revisarPortal` (en `extension/servicio.js`) abre una pestaña en segundo plano con `abrirPestana`, comprueba que siga en el portal (`plataformaDeUrl`, `paginaPermitida`), inyecta el motor y ejecuta funciones de `globalThis.__asistente` con los selectores del servidor. Después cierra la pestaña.
- El latido (`POST /api/v1/latido`, cada `latido_s`) es el único canal del servidor hacia la extensión. Hoy devuelve `trabajo`, `selectores`, `cuentas`, etc., y la extensión solo actúa sobre lo que recibe.
- Los JSON de selectores (`assets/asistente/selectores/*.json`) llevan `version`, `verificado` y una sección por flujo (`sesion`, `cuenta`, `perfil`, `postular`). El servidor los sirve y la extensión no ejecuta código remoto: solo interpreta datos.
- Lo conocido por `docs/asistente/portales.md`:
  - Computrabajo lista las postulaciones en `/co/estadisticas/mis-procesos/` y tarda minutos en reflejar una nueva;
  - Magneto las lista en `/profile/processes` («Procesos activos», cada una con «Aplicación enviada» y fecha).

  No se sabe aún qué estados posteriores muestran.
- El seguimiento (`seguimiento-proceso-postulacion`) expone `Procesos.registrar` y `Procesos.abrir`, y guarda en `procesos.id_oferta` el id de la oferta en el portal.

## Goals / Non-Goals

**Goals:**
- Reusar el canal del latido y el motor existentes, sin permisos nuevos de la extensión para Computrabajo y Magneto.
- Que agregar un portal sea agregar datos al JSON, no código.

**Non-Goals:**
- Responder mensajes, aceptar entrevistas, retirar postulaciones o cualquier otra acción en el portal.
- LinkedIn, GetOnBoard y SPE.
- Leer el contenido completo de los mensajes del portal (solo el contador y, si se ve sin abrir, remitente y asunto).

## Decisions

### 1. El servidor programa, la extensión obedece
- La respuesta del latido agrega `procesos: ["computrabajo", ...]`. El servidor guarda por usuario y portal la hora de la última lectura pedida y la de la última recibida, en `procesos_portal_foto`.
- Se pide de nuevo solo si pasaron `cada_h` horas desde la última recibida, o `reintento_h` (1 h por defecto) desde la última pedida sin respuesta.
- **Por qué no un `chrome.alarms` propio:** el servidor ya conoce la sesión, la ventana horaria del usuario y si hay un trabajo en curso. Así la frecuencia se cambia en `config.yaml` sin publicar la extensión.

### 2. Lector genérico de filas en `motor.js`
Una función `leerFilas(sel.procesos)` recorre `fila` y saca de cada una los `campos`, cada uno como selector más atributo o texto. También sigue un `siguiente` opcional hasta `max_paginas` (1 por defecto) y devuelve también `mensajes` si está declarado. La sección del JSON queda así:

```json
"procesos": {
  "verificado": false,
  "url": "https://co.computrabajo.com/co/estadisticas/mis-procesos/",
  "fila": "…",
  "campos": {"cargo": "…", "empresa": "…", "fecha": "…", "estado": "…", "enlace": "a@href"},
  "id_oferta": "oferta-de-trabajo-de-.*-([0-9A-F]{32})",
  "estados": {"postulado": "enviado", "cv visto": "cv_visto", "en proceso": "en_proceso",
              "finalista": "entrevista", "descartado": "descartado"},
  "mensajes": {"url": "…", "contador": "…", "items": "…", "remitente": "…", "asunto": "…"}
}
```

Los textos del mapa `estados` se comparan normalizados (minúsculas, sin tildes, con `normalizar.py` en el servidor). **Los valores del ejemplo son provisionales** hasta el reconocimiento.

### 3. Foto completa y comparación en el servidor
- La extensión manda `POST /api/v1/procesos/{plataforma}` con `{estado: "ok"|"sin_sesion", filas: [...], mensajes: {sin_leer, items}, version_selectores}`.
- El servidor (`procesos_portal.py`) guarda la foto normalizada (JSON) y la compara con la anterior.
- **Por qué foto completa y no deltas calculados en la extensión:** la extensión no guarda estado de negocio, la lógica se prueba en Python y una caída a mitad de camino no deja nada a medias.
- Las filas no se guardan más allá de la última foto.

### 4. Asociación
1. Primero por `id_oferta` contra `procesos.id_oferta`. Ese dato se llena al abrir el proceso desde la URL de la vacante, con la misma expresión del JSON.
2. Si no hay id, por empresa y cargo normalizados dentro del mismo portal, con seguridad `media`, que el seguimiento convierte en una pregunta de confirmación.
3. Si tampoco hay coincidencia, la oferta va a la oferta de proceso externo, con un registro en `kv` (`externo_ofrecido:{usuario}:{plataforma}:{id}`) para preguntar una sola vez.

### 5. Primera foto sin ruido
En la primera lectura de un usuario y portal no se envían avisos con sonido. Solo se registran los avances sobre el estado actual (decisión del spec). Así, al activar la función, no llegan veinte avisos de golpe.

### 6. Incidentes por marcado roto
- Si hay sesión y la foto sale con 0 filas cuando la anterior tenía 1 o más, o si más de la mitad de las filas traen estados sin mapear, se avisa al dueño con `_avisar_dueno`, una vez por día y portal.
- La foto anterior se conserva.

## Risks / Trade-offs

- [Los términos del portal sobre automatización] → Solo lectura de la propia cuenta, como mucho cuatro veces al día, en horario diurno y sin acciones. Se documenta en `portales.md` junto a la revisión de términos existente, y el dueño decide antes de activar cada portal (`procesos.verificado`).
- [La extensión solo corre con el navegador abierto] → La lectura se hace en la siguiente ocasión en que esté abierto. El correo (`correo-seguimiento-reenvio`) cubre las horas sin navegador.
- [La pestaña en segundo plano molesta al usuario] → Se usa la misma pestaña en segundo plano que la revisión de sesión, se cierra en segundos y nunca se activa (la verificación de captcha no aplica aquí: si aparece, se aborta la lectura).
- [Los estados del portal cambian de texto] → Los textos sin mapear no generan eventos y se avisan al dueño. El mapa se corrige en el JSON sin publicar la extensión.
- [Paginación] → Solo se leen las más recientes (`max_filas`, `max_paginas`). Los procesos viejos ya cerrados no importan.

## Migration Plan

1. Reconocimiento y fixtures (👤).
2. Desplegar el servidor con `procesos.verificado: false`: no se pide ninguna lectura.
3. Publicar la extensión con el lector y recargarla.
4. Activar `verificado: true` por portal, con un piloto sobre la cuenta del dueño.
5. **Para volver atrás:** `verificado: false` en el JSON, sin redeploy de la extensión.
