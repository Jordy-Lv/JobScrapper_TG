## Context

- `panel-admin-metricas` deja listos el router `/panel/`, la sesión con CSRF, el selector de periodo y la tabla `metricas_dia_asistente`. Este change agrega secciones a esa base sin cambiarla.
- La membresía se comprueba hoy con `getChatMember` (`membresia.Comprobador`) al interactuar y cada `comprobar_cada_h` horas. `Usuarios.aplicar_membresia` suspende o reactiva según el resultado.
- `bot.py` registra los handlers. `servicio.py` arranca el polling con `allowed_updates=Update.ALL_TYPES`, que ya incluye `chat_member`. El bot asistente es administrador del grupo, una condición que Telegram pone para entregar `chat_member`.
- Telegram da el número de miembros (`getChatMemberCount`), pero no la lista.

## Goals / Non-Goals

**Goals:**
- Reutilizar `Usuarios.suspender`, `reactivar` y `aplicar_membresia`, sin una segunda versión de esas reglas.
- Que las consultas de usuarios y postulaciones respondan rápido con cientos de usuarios y miles de postulaciones.

**Non-Goals:**
- Enviar mensajes a usuarios desde el panel.
- Borrar usuarios desde el panel. `/borrarme` sigue siendo del usuario, y la inactividad se borra sola.
- Ver o editar el perfil, el CV o las respuestas.

## Decisions

### D1. `ChatMemberHandler` del grupo en `bot.py`, con la lógica en `membresia.py`
`ChatMemberHandler(..., ChatMemberHandler.CHAT_MEMBER)` filtra por el `chat_id` del grupo y llama a `Comprobador.aplicar_aviso(old, new, ahora)`. Ese método:
1. calcula si entró o salió, con `interpretar_miembro` para el estado viejo y el nuevo;
2. busca al usuario del bot por `telegram_id`, sin crearlo;
3. si existe, llama a `aplicar_membresia` y actualiza la caché de membresía;
4. inserta en `eventos_grupo` la hora, el tipo y si es usuario.

- *Alternativa*: seguir solo con la comprobación periódica. Un usuario que sale seguiría pudiendo postular hasta 24 horas.

### D2. `eventos_grupo` sin datos personales
```
eventos_grupo(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, tipo TEXT NOT NULL, -- entrada | salida
              es_usuario INTEGER NOT NULL)
```
La tabla está en el esquema 5 de `asistente.db` y se limpia con `asistente.retencion_dias`. El resumen diario de `comun/metricas.py` suma `entradas`, `salidas` y `miembros` (el conteo de `getChatMemberCount` tomado en el resumen de cada hora) en `metricas_dia_asistente`, con dimensión `grupo`, para conservarlos `dias_metricas` días. La fecha de activación se guarda en `kv` (`panel_grupo_desde`) para el aviso «sin registro antes del…».

### D3. Consultas de usuarios en vivo y no en el resumen
La tabla y la ficha leen `usuarios`, `navegadores`, `cuentas_portal` (solo `plataforma` y `estado`, nunca el correo) y `postulaciones` en el momento. Los conteos del periodo se hacen con una sola consulta agrupada por `usuario_id`. El embudo de altas se calcula a partir de:
- `creado` y `politica_aceptada_en`;
- `cv_archivo` no nulo;
- `gemini_valida = 1`, o cualquier proveedor válido según el esquema de `ia-multiproveedor-asistente`;
- que exista algún `navegadores`;
- que exista alguna `postulaciones` con `tipo = 'postular'`.

Una lista blanca explícita de columnas en `panel/consultas_usuarios.py` asegura que ningún campo personal llegue al JSON. Una prueba lo comprueba recorriendo las claves de la respuesta.

### D4. Acciones con POST y confirmación en la página
`POST /panel/datos/usuarios/{id}/suspender` y `/reactivar` exigen la sesión, el CSRF y que el estado actual permita la acción (si no, 409). Llaman a `Usuarios.suspender` o `reactivar` con el `telegram_id` del admin como actor. La confirmación es un diálogo `<dialog>` nativo.

### D5. Postulaciones: totales del resumen y tabla en vivo
- **Totales y series**: desde `metricas_dia_asistente`, que `panel-admin-metricas` ya guarda por plataforma, estado y origen.
- **Motivos de fallo, mediana de duración y tabla**: desde `postulaciones` en vivo, dentro de `retencion_dias` (90). Fuera de ese plazo se muestra el mismo aviso de detalle borrado.

## Risks / Trade-offs

- [Telegram no entrega `chat_member` si el bot pierde el rol de administrador] → La comprobación periódica sigue igual como respaldo. La vista Grupo muestra la hora del último aviso recibido.
- [Avisos duplicados o fuera de orden] → `aplicar_membresia` es idempotente. Los conteos pueden tener un evento de más, lo que se acepta para un indicador.
- [Conteo de miembros desactualizado] → Caché de `grupo.cache_min` minutos y la hora de la consulta en pantalla.
- [Ver la lista de usuarios es tratamiento de datos] → Se muestran solo los datos que la política ya cubre (nombre de Telegram, estado, actividad). El acceso es solo de admins y queda auditado (`panel_usuarios_listar`, `panel_usuario_ver`).

## Migration Plan

1. Desplegar después de `panel-admin-metricas`. `asistente.db` sube al esquema 5 y se guarda `panel_grupo_desde`.
2. Probar con una cuenta de prueba que sale y vuelve al grupo: suspensión y reactivación en el acto, más el conteo de entradas y salidas.
3. Vuelta atrás: el código anterior ignora `eventos_grupo` y sigue con la comprobación periódica.
