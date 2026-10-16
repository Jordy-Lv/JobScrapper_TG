## Context

`procesar_toque` (`conversacion.py`) llama a `n.tocar`, que encola la vacante y, si es automática, deja que `_preparar` y la extensión sigan. La card (`tarjeta_postulacion.py`) se identifica por `pid` y se guarda en `kv` como `card:{pid}`; la animación del progreso ya edita esa card con `_animar_progreso` e `intervalo_animacion` (2,5 s). Antes de encolar no existe `pid`. Ver proposal.md para la motivación.

## Goals / Non-Goals

**Goals:**
- Que ninguna postulación exista en la cola durante la cuenta, para que no haya nada que deshacer en la cola ni en la extensión.
- Reutilizar el patrón de animación por edición y la regla de una sola card.

**Non-Goals:**
- Cancelar una postulación ya encolada o en curso (sería otro change).
- Cuenta regresiva en «Reintentar», en el paquete de respaldo ya enviado ni en cualquier flujo de la extensión.

## Decisions

1. **La cuenta vive antes de la cola.** `procesar_toque` valida (pausa, vacante disponible, no existe ya) y arranca la cuenta; recién al terminar llama a `n.tocar`. Alternativa descartada: encolar en un estado nuevo «en_espera» y cancelarlo; obliga a tocar `cola.py`, el estado de la extensión y los reportes, para algo que dura 5 s.
2. **Estado previo al `pid` en `kv`:** clave `cuenta:{usuario_id}:{id_corto}` con `{mensaje_id, vence}`, y una tarea en memoria `_cuentas[(usuario_id, id_corto)]`. La card de la cuenta es un `Card` con fases nuevas `cuenta` y `cancelada`, pintado con el `id_corto` en lugar del `pid`; al terminar, el mensaje se adopta como `mensaje_id` de la card del `pid` real (la ruta ya existe para la tarjeta del alta).
3. **Animación:** una edición por segundo (con `intervalo_animacion` de 2,5 s habría solo 2 cuadros en 5 s), con barra `▰▰▰▱▱` y «Postulando en N s». Una edición fallida se ignora: un cuadro perdido lo atrapa el siguiente, igual que en el progreso. El cierre (encolar o cancelar) siempre se pinta.
4. **Fuera del candado.** El candado del usuario se toma solo para validar y para encolar al final; la espera no lo retiene, así otras acciones del usuario no se bloquean.
5. **Botones:** `cb("cancel", id_corto)` y, en la card cancelada, `cb("post", id_corto)` que reabre la cuenta sobre el mismo mensaje. «Cancelar» tardío (ya no hay cuenta) responde con aviso corto y no cambia la card.
6. **Doble toque:** si ya hay tarea en `_cuentas` para esa clave, se responde sin hacer nada más. El canal responde de inmediato: «⚡ Tienes 5 s para cancelar en el bot».
7. **Reinicio:** al arrancar se leen las claves `cuenta:*` pendientes, se borran y sus cards pasan a la fase `cancelada` con el texto «La cuenta se interrumpió; no envié nada». Se prefiere descartar a postular, porque el usuario podría haber querido cancelar y ya no puede.
8. **Alta pendiente:** `en_tarjeta=True` usa la misma cuenta, pintada en la tarjeta del alta (conserva el bloque de conexión); es el caso de la captura que originó el cambio.
9. **Configuración:** `asistente.cuenta_regresiva_segundos` (entero ≥ 0, 5 por defecto); 0 conserva el comportamiento actual, lo que además mantiene simples las pruebas existentes.

## Risks / Trade-offs

- [Límite de ediciones de Telegram] → una edición por segundo y cinco por toque; un error de límite salta el cuadro.
- [El usuario espera 5 s aunque no dude] → configurable y desactivable con 0.
- [Pruebas que esperan «En cola» al instante] → se fija la cuenta en 0 en el fixture común y se añaden pruebas propias de la cuenta con espera inyectable.
- [El `kv` queda con restos si el proceso muere sin limpiar] → el barrido de arranque los borra.
