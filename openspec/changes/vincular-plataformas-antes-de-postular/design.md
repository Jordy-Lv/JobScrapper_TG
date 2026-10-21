## Context

Hoy el alta termina así: el usuario toca «Vincular mi navegador» (paso `navegador`), la extensión canjea el código, la API emite el aviso `navegador_vinculado` y `_avisar_dict` marca la tarjeta y llama a `_terminar_alta`. Esta completa el alta y, con `vacante_pendiente`, llama a `procesar_toque(..., en_tarjeta=True)`, que encola la postulación. A partir de ahí el latido de la extensión reporta cada portal (`sin_sesion`, o la cuenta con `cuenta_por_confirmar`, `cuenta_distinta`, `portal_listo`, `portal_incompleto`) y la tarjeta (`tarjeta.py`) ya muestra una línea por portal y los botones «Confirmar»/«Cancelar».

Todo lo necesario para saber si la sesión está confirmada ya existe: el estado `CONFIRMADA` en la tarjeta y la tabla `cuentas_portal`. Lo que falta es **esperarlo** antes de postular. Ver proposal.md para la motivación.

## Goals / Non-Goals

**Goals:**
- Un paso explícito del alta, `plataformas`, que retiene el cierre y el arranque de la vacante hasta confirmar la cuenta.
- Reutilizar los avisos, la tarjeta y los botones existentes.

**Non-Goals:**
- No cambia la extensión, la API de latido ni la cola.
- No obliga a confirmar todas las plataformas.
- No cambia qué pasa con los usuarios que ya terminaron el alta (el flujo normal con `ESPERANDO_SESION` se queda igual).

## Decisions

1. **Nuevo `paso_alta = "plataformas"`** entre `navegador` y el cierre. `navegador_vinculado` ya no llama a `_terminar_alta` directo: llama a `_ir_a(usuario, "plataformas")`. Alternativa descartada: un indicador aparte sobre el paso `navegador`, porque `_continuar_alta` y el reintento con `/start` ya se apoyan en el valor de `paso_alta`.

2. **Qué cumple el paso.** `_plataforma_esperada(usuario)` devuelve la plataforma de `vacante_pendiente` (resuelta con `n.indice.resolver`) o `None` si no hay vacante. El paso se cumple cuando la tarjeta tiene esa plataforma en `CONFIRMADA` o `COMPLETANDO` (sesión y cuenta ya validadas; el perfil se completa por la cola), o, sin vacante, cuando cualquiera lo está. Se evalúa tras `portal_listo`, `portal_incompleto` y el botón `cuenta:<p>:si`. Alternativa descartada: exigir todas las plataformas, que bloquearía a quien solo usa una.

3. **Salto del paso.** Al entrar a `plataformas`, `_paso_cumplido` se evalúa de una vez con dos fuentes: la tarjeta y los portales que el último latido de los navegadores del usuario dejó guardados (`navegadores.portales_json`, con `cuenta == "ok"` y estado distinto de `sin_sesion`/`sin_permiso`). Así una reinstalación no obliga a esperar un aviso que no volverá (el latido solo avisa al cambiar de estado). También se salta si la plataforma de la vacante no está en `config.plataformas` con `automatica: true` (esa vacante irá a respaldo y no necesita sesión).

4. **Omitir.** Botón `cb("omitir_plat")` en la tarjeta del paso → `_terminar_alta`, que ya encola la vacante pendiente; la cola espera la sesión como hoy. Es la salida para quien no quiere o no puede iniciar sesión ahora.

5. **Tarjeta.** `tarjeta.lineas` ya muestra «· X: inicia sesión…» por portal solo si hay cuentas; en el paso se siembran las plataformas automáticas como `PENDIENTE` para que se vean desde el principio, y la esperada se marca como la que se necesita. Se retira del texto genérico final la línea «Inicia sesión en Computrabajo, Magneto y elempleo». `_terminar_alta` conserva su lógica y se llama solo desde el cierre del paso.

6. **Textos.** `textos.NAVEGADOR` queda con «Paso 5 de 6 · Vincula tu navegador» (sin el punto 3 de iniciar sesión) y se agrega `PLATAFORMAS` («Paso 6 de 6 · Inicia sesión en tus portales…»). Los demás «de 5» del alta pasan a «de 6».

7. **Retomar con `/start`.** `_continuar_alta` con `plataformas` reenvía la tarjeta como mensaje nuevo, borra la anterior (mejor esfuerzo) y avisa que la vacante sigue guardada, igual que `reenviar-tarjeta-preguntas-al-retomar-alta`. Si ese change aún no está unido, se implementa aquí el mismo patrón sin depender de él.

## Risks / Trade-offs

- [El usuario nunca inicia sesión y deja el alta abierta] → «Omitir por ahora» y el recordatorio ya existente de alta incompleta.
- [El latido tarda hasta `latido_s` segundos en reportar la sesión] → la tarjeta lo dice («puede tardar unos segundos») y el salto de la decisión 3 cubre las sesiones ya reportadas.
- [Un usuario a medias en el paso 5 al desplegar] → su `paso_alta` sigue siendo `navegador`; al vincular pasa por el paso nuevo, sin migración.
- [Una plataforma sin selectores cargados nunca aparece en el latido] → la lista del paso toma solo las plataformas con `automatica: true`, que ya exigen selectores.

## Migration Plan

Sin cambios de esquema ni de configuración. Desplegar con `git pull --ff-only` y reiniciar `buscador-asistente` en el Fedora. Reversión: volver al commit anterior; los usuarios con `paso_alta = "plataformas"` caerían sin paso conocido en `_continuar_alta`, por lo que antes de revertir se les pasa a `navegador` o se completa su alta.
