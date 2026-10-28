## Why

La postulación 43 (Magneto, 2026-10-17) se quedó en «En cola. Te aviso el resultado» sin avanzar: el latido de la extensión reportaba «magneto sin sesión: enlace_ingresar» y el servidor solo asigna trabajos de portales con sesión y cuenta confirmadas (`cuentas` en la respuesta del latido). La card no dijo nada, así que el usuario no tenía cómo saber que debía iniciar sesión. Lo mismo pasa con cualquier otra causa que frena la cola sin que el flujo llegue a correr (permiso de dominio, extensión vieja, cuenta por confirmar, plataforma pausada), en los tres portales.

## What Changes

- El servidor guarda, en cada latido, el estado completo de cada portal del navegador (sesión y su motivo, cuenta, ausencia por falta de permiso), incluido el caso «sin sesión» que hoy no se guarda.
- Un diagnóstico nuevo calcula, para cada postulación en cola, la causa concreta de la espera, en un orden fijo de prioridad y para cualquier plataforma (Computrabajo, Magneto, elempleo):
  - sin navegador vinculado, o navegador sin latido reciente;
  - extensión por debajo de `version_minima`;
  - plataforma apagada con `/plataformas` (o sin selectores cargados);
  - permiso de dominio del portal sin activar en la extensión (p. ej. elempleo.com);
  - sin sesión iniciada en el portal;
  - cuenta del portal por confirmar, de otra persona o con correo ilegible;
  - perfil del portal en revisión o completándose;
  - esperas normales de la cola: otra postulación en curso, tope diario y pausa entre postulaciones (añadidas para que «en cola» nunca quede sin explicación).
- La card en fase «en cola» muestra el mensaje de esa causa y su solución, con botón cuando existe uno: «Iniciar sesión» (abre el login del portal) y «Crear cuenta», «Vincular navegador», «Actualizar extensión» (si hay tienda configurada), «Confirmar»/«Cancelar» y «Es mi cuenta nueva»/«No es mía» para la cuenta.
- La card se actualiza sola: tras cada latido, cada minuto de vigilancia y cada cambio con `/plataformas`, se recalcula la causa y la card se edita solo si cambió. Cuando la causa se resuelve vuelve a «En cola. Te aviso el resultado» y sigue su camino normal.
- Con una plataforma apagada por `/plataformas`, la asignación deja de entregar trabajos de esa plataforma mientras esté apagada (hoy solo se respeta al tocar «Postular»), para que el mensaje «pausada» sea verdad. Al encenderla, la cola sigue sola.
- La extensión envía en el latido si el usuario la puso en pausa (campo opcional `pausado`), para que esa causa también se explique.
- Sin cambios en el flujo de postulación de la extensión (`motor.js`, pasos) ni en los selectores.

## Capabilities

### New Capabilities
- `espera-postulacion-asistente`: diagnóstico de por qué una postulación en cola no se asigna, a partir del último latido de cada navegador, la configuración de plataformas y las reglas de la cola.

### Modified Capabilities
- `tarjeta-postulacion-asistente`: la card en cola explica la causa de la espera con su solución y sus botones, y se actualiza sola cuando la causa cambia o se resuelve.

## Impact

- `buscador_vacantes/asistente/api.py`: el latido guarda el estado completo de cada portal en `navegadores.portales_json`, acepta `pausado`, excluye plataformas apagadas de lo asignable y avisa a la conversación para recalcular las esperas.
- Módulo nuevo `buscador_vacantes/asistente/espera.py` (funciones puras del diagnóstico) y `cola.py` (consultas de tope, pausa y postulación activa reutilizables por el diagnóstico).
- `tarjeta_postulacion.py`, `conversacion.py` y `textos.py`: textos y botones por causa, URL de ingreso por portal, repintado de las cards en cola.
- `extension/servicio.js`: solo añade `pausado` al cuerpo del latido.
- Pruebas en `tests/asistente/` (api, nucleo/conversación, tarjeta, espera nuevo). Sin migración de esquema: `portales_json` ya es texto JSON.
- Convive con los changes en curso que modifican «Estados de la card» (`preguntas-encuesta-con-botones-y-redaccion-ia`): aquí se agrega un requisito aparte para no chocar con esa delta.
