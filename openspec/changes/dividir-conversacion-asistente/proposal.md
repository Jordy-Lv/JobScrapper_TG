## Why

`buscador_vacantes/asistente/conversacion.py` tiene 2.342 líneas y una sola clase, `Conversacion`, con unos 110 métodos. Mezcla el alta, la lectura del CV, el cuestionario, las tarjetas, la postulación, los comandos, los avisos, el progreso y los mensajes efímeros. Su método `al_boton` es un `match` de 215 líneas con 25 casos. Todo cambio del bot cae en este archivo:
- los changes abiertos `preguntas-encuesta-con-botones-y-redaccion-ia` y `reenviar-tarjeta-preguntas-al-retomar-alta` lo tocan;
- también lo toca `ia-multiproveedor-asistente`.

Así aumentan los conflictos entre ramas, cuesta encontrar dónde vive cada flujo y una edición en un caso del `match` puede romper otro. Es la fase 3 del plan de reestructura (ADR 0001) y no debe cambiar nada de lo que ve el usuario.

## What Changes

- `asistente/conversacion.py` pasa a ser el paquete `asistente/conversacion/`, con un módulo por flujo: alta, CV y perfil, cuestionario, tarjetas, postulación, comandos y avisos. Una base común reúne los tipos, el estado y las utilidades. Ningún módulo pasa de unas 500 líneas.
- `Conversacion` sigue siendo una sola clase con la misma interfaz. Se arma con las piezas de cada flujo, y `from buscador_vacantes.asistente.conversacion import Conversacion, Bloqueado, Botones, cb, botones_proveedores` sigue funcionando sin cambios en `bot.py`, `servicio.py` ni en las pruebas.
- El `match` de `al_boton` se reemplaza por un **registro de manejadores**: cada flujo declara los prefijos de botón que atiende (`@boton("politica")`), y `al_boton` busca el prefijo y llama al manejador. Un prefijo repetido falla al importar. Un prefijo desconocido se ignora, como hoy.
- Pruebas nuevas:
  - pruebas de caracterización de los casos de botón que hoy no están cubiertos, escritas **antes** de mover código;
  - una prueba que exige que cada `cb("prefijo", …)` del código tenga manejador y que no sobren manejadores;
  - una prueba de estructura que limita el tamaño de cada módulo y prohíbe que los flujos se importen entre sí.
- **Sin cambios de comportamiento.** Los mismos mensajes, botones, datos de callback, orden de envío, estados guardados y esquemas SQLite. `config.yaml`, la API para la extensión y los nombres de los métodos públicos y privados que usan `servicio.py` y las pruebas tampoco cambian.
- **Fuera de alcance:**
  - reescribir la lógica de cada flujo o renombrar métodos;
  - convertir `al_texto` o `al_comando` en registros (ya son despachos cortos y legibles);
  - separar la conversación en objetos independientes por composición (ver `design.md`).

## Capabilities

### New Capabilities

### Modified Capabilities

Ninguna: es un refactor interno sin cambio de comportamiento (`skip_specs: true`). Las reglas de estructura quedan en `design.md` y las hacen cumplir las pruebas.

## Impact

- **Código:** `buscador_vacantes/asistente/conversacion.py` se convierte en el paquete `buscador_vacantes/asistente/conversacion/`, de unos 10 módulos. Ningún otro módulo de producción cambia.
- **Pruebas:**
  - `tests/asistente/test_bot.py` recibe pruebas de caracterización, sin tocar aserciones existentes;
  - nuevas `tests/asistente/test_conversacion_estructura.py` (registro de botones y tamaño de módulos).
- **Despliegue:** `git pull` y reinicio de `buscador-asistente` en el Fedora. El radar no se ve afectado.
- **Changes abiertos:** se actualizan las rutas en los planes de `preguntas-encuesta-con-botones-y-redaccion-ia`, `reenviar-tarjeta-preguntas-al-retomar-alta` e `ia-multiproveedor-asistente`; solo los textos, no su código.
- **Riesgo:** al mover más de 2.000 líneas, un método puede quedar sin clase o un caso del `match` puede cambiar de sentido. Mitigación:
  - caracterizar primero;
  - mover el código tal cual, sin reescribirlo;
  - commits pequeños con la suite en verde;
  - la prueba de cobertura del registro de botones.
