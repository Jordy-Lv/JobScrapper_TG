## Context

Ver proposal.md (Why). Medición del 2026-10-14 sobre `buscador_vacantes/asistente/conversacion.py`:

- **Nivel de módulo:**
  - tipos: `Salida`, `Bloqueado`, `Botones`, `RespuestaToque`, `Opciones`;
  - funciones: `cb`, `botones_proveedores`, `derivar_del_cv`;
  - constantes: `SECCIONES`, `NOMBRE_SECCION`, `PROVEEDORES_*`, `MENSAJE_GUIA_PROXIMAMENTE`.
- **Estado de la instancia** (`__init__`): `n`, `s`, `comprobador`, `config`, `reloj`, `dormir`, `_mensajes`, `_candados`, `_tareas`, `_borrados`, `_toques_resumen`, `intervalo_animacion`, `_etapas` y `_animaciones`.
- **Quién la usa desde fuera:**
  - `bot.py` importa `Bloqueado`, `Botones` y `Conversacion`;
  - `servicio.py` llama a `notificar`, `procesar_toque`, `recordatorios`, `borrar_vencidos`, `esperar_tareas`, `comprobador` y al privado `_enviar`;
  - `tests/asistente/test_bot.py` (1.790 líneas) usa `al_boton` (87 veces), `notificar` (43), `al_texto`, `al_comando`, `al_iniciar`, `al_toque_canal`, `procesar_toque`, `esperar_tareas`, `borrar_vencidos`, `dormir` e `intervalo_animacion`, y los privados `_preguntas`, `_guardar_preguntas`, `_iniciar_preguntas`, `_esperando` y `_detener_progreso`.
- **Nada parchea rutas internas del módulo** (`monkeypatch` o `patch("…conversacion.X")`).
- **`al_boton` tiene 25 casos.** Los datos de callback se arman con `cb(...)` en `conversacion.py`, `tarjeta.py`, `tarjeta_postulacion.py` y `preguntas_tarjeta.py`. El caso `alta` no tiene productor visible con un prefijo literal, así que puede venir de mensajes viejos.
- **Los botones ya enviados guardan su callback en Telegram.** Un manejador que hoy no tiene productor todavía puede recibir toques de mensajes antiguos.

## Goals / Non-Goals

**Goals:**
- Módulos por flujo de 500 líneas o menos, con límites claros y verificados por pruebas.
- Un registro de botones donde agregar un flujo no obliga a editar un `match` central.
- Equivalencia exacta de comportamiento, demostrada con pruebas que existen **antes** de mover el código.
- Historial de git rastreable.

**Non-Goals:**
- Cambiar la lógica, los textos, los datos de callback o los nombres de los métodos.
- Hacer públicos los métodos privados que usan `servicio.py` y las pruebas. Se puede hacer en un change aparte.
- Registros para `al_texto` (despacho por `esperando.tipo`) o `al_comando` (ya es un diccionario).
- Borrar manejadores sin productor, que pueden servir a mensajes antiguos.

## Decisions

### 1. Paquete con mixins por flujo, no composición
`asistente/conversacion/` queda así:

| Módulo | Contenido (rangos actuales aproximados) | Prefijos de botón |
|---|---|---|
| `base.py` | tipos y funciones de módulo (`Salida`, `Bloqueado`, `Botones`, `cb`, `RespuestaToque`, `Opciones`); `ConversacionBase` con `__init__` y utilidades (`es_dueno`, `_permitir`, `_esperando`, `_esperar`, `_en_segundo_plano`, `esperar_tareas`, `_enviar`); el decorador `boton` | — |
| `alta.py` | `al_iniciar`, política, `_continuar_alta`, `_ir_a`, clave y proveedores (`botones_proveedores`), `_mostrar_navegador`, `_terminar_alta`, `_alta_lista` (225–351, 953–988) | `politica`, `clave`, `provpag`, `prov`, `alta` |
| `perfil.py` | `derivar_del_cv`, `SECCIONES`, `al_documento`, lectura del CV con reintentos, perfil manual, secciones, resumen y enfoque (352–725) | `cvopc`, `cv`, `seccion`, `enfoque`, `resumen`, `perfil` |
| `cuestionario.py` | cuestionario y preguntas de la tarjeta (726–952) | `cuest` |
| `tarjetas.py` | tarjeta de conexión y card de postulación (984–1150) | `cuenta` |
| `postulacion.py` | `procesar_toque`, `al_toque_canal`, `_preparar`, paquete, pegadas y pendientes (1151–1305, 1350–1441) | `pend`, `pegar`, `editar`, `res`, `rei`, `seg`, `guia` |
| `comandos.py` | vinculación, `al_comando`, `_c_*` y `_a_*` (1657–2001) | `vincular`, `nav`, `borrarme`, `pausa` |
| `avisos.py` | `notificar`, avisos de eventos, progreso, resumen, mensajes efímeros, `borrar_vencidos` y `recordatorios` (2002–2342) | `cerrar` |
| `principal.py` | `class Conversacion(Alta, Perfil, Cuestionario, Tarjetas, Postulacion, Comandos, Avisos, ConversacionBase)`, `al_texto` y el despachador `al_boton` | — |
| `__init__.py` | reexporta los nombres públicos actuales | — |

La tabla es la guía. La tarea 2.1 fija el reparto exacto método por método, leyendo el código, y lo anota aquí si cambia. Cada mixin hereda de `ConversacionBase` para que el estado y las utilidades sigan en `self`.

*Alternativa descartada: composición* (objetos `FlujoAlta`, `FlujoCV`… que reciben un contexto). Da límites más fuertes, pero los flujos se llaman entre sí unas 60 veces. Algunos ejemplos: los comandos llaman a `_continuar_alta`, los botones a `procesar_toque` y el cuestionario a `_pintar_card`. Convertir cada llamada exige reescribir código y cambiar las pruebas que usan métodos privados. Con mixins el código se mueve tal cual y `self.metodo()` sigue resolviendo igual. La composición se puede hacer después, flujo por flujo, sobre módulos ya pequeños.

### 2. Registro de botones con decorador
`boton(*prefijos)` marca un método con los prefijos que atiende. Al definir `Conversacion`, una función recorre la MRO y arma el diccionario `prefijo → método`. Si un prefijo aparece dos veces, lanza `ValueError` al importar. Cada caso del `match` pasa a un método `_b_<prefijo>(self, usuario, args, ahora) -> str | None` con el **mismo cuerpo**. Dentro del cuerpo, `tid` pasa a ser `usuario.telegram_id`, que es el mismo valor, porque `usuario` se obtiene por `tid`.

`al_boton` conserva su preámbulo:
- obtiene el usuario;
- exige el prefijo `cb:`;
- separa la acción de los argumentos;
- calcula `ahora`.

Después busca el manejador. Un prefijo desconocido devuelve `None`, como un `match` sin caso. Los manejadores que hoy terminan sin `return` devuelven `None`, como antes.

*Alternativa descartada:* un diccionario escrito a mano en `al_boton`. Volvería a centralizar la lista que se quiere repartir.

### 3. Caracterizar antes de mover
Antes de tocar la estructura se mide la cobertura de `conversacion.py` con `uv run --with pytest-cov pytest tests/asistente/test_bot.py --cov=buscador_vacantes.asistente.conversacion --cov-report=term-missing`. Esto no cambia `pyproject.toml`. Con el resultado:
- Se agrega una prueba de caracterización por cada caso de `al_boton` sin cubrir. La prueba fija los mensajes, botones y estados que produce hoy.
- Se cubre también cualquier rama de `al_texto` sin cubrir.

Esas pruebas se confirman en `main` como commit propio y deben pasar **antes** y **después** del refactor.

### 4. Movimiento en commits pequeños y sin reescribir
1. `git mv conversacion.py conversacion/principal.py`, con un `__init__.py` que reexporta. La suite queda en verde.
2. Un commit por flujo: se corta el bloque de métodos de `principal.py` y se pega en su módulo **sin cambios de texto**, salvo la sangría si hiciera falta. La suite queda en verde tras cada commit.
3. Un commit aparte para el registro de botones.

`git log --follow` sigue a `principal.py`. Para los bloques extraídos se usa `git blame -C -C`.

### 5. Pruebas de estructura
En `tests/asistente/test_conversacion_estructura.py`:
- **Registro completo:** se recorre `buscador_vacantes/asistente/` con `ast` y se recogen los primeros argumentos literales de cada llamada `cb("…", …)`.
  - Cada prefijo recogido tiene manejador.
  - Cada manejador sin productor está en la lista explícita `HEREDADOS` de la prueba, con un comentario sobre su origen. Hoy `alta` queda ahí si la tarea 2.1 confirma que no tiene productor.
- **Tamaño:** ningún módulo de `asistente/conversacion/` pasa de 500 líneas.
- **Límites:** los módulos de flujo importan de `base` y de módulos ajenos al paquete, pero no entre sí. Solo `principal.py` los junta.

### 6. Orden respecto a los changes abiertos
`preguntas-encuesta-con-botones-y-redaccion-ia` (0 de 10 tareas) y `reenviar-tarjeta-preguntas-al-retomar-alta` (0 de 8) aún no tienen código. Según el criterio que el dueño ya fijó en la reestructura (reestructurar sin esperar a los changes con trabajo pendiente y adaptar después sus planes), este change va primero. Después se actualizan las rutas y los nombres de los métodos en sus planes. El dueño lo confirma en la tarea 1.2.

`portales-en-un-solo-lugar` no toca `conversacion.py`, así que puede ir antes o después. Se recomienda antes, porque es más corto.

## Risks / Trade-offs

- [Un método queda fuera de la clase al moverlo] → `Conversacion` reúne todos los mixins. Además, una prueba compara el conjunto de métodos de `Conversacion` antes y después, con una lista congelada sacada de `dir(Conversacion)` en la tarea 1.3.
- [Un caso del `match` cambia de sentido al volverse método, por variables locales compartidas o `return` implícito] → El cuerpo se copia sin reescribir, se revisan los usos de `tid`, `data`, `partes` y `ahora`, y las pruebas de caracterización cubren cada prefijo.
- [Los mixins esconden de dónde viene un atributo] → Todo el estado vive en `ConversacionBase.__init__` y ningún mixin define `__init__`. Una prueba de estructura lo comprueba.
- [Conflictos con trabajo en otras ramas] → La tarea 1.1 confirma que nadie más trabaja sobre `conversacion.py`, y los planes abiertos se actualizan al final.
- [La suite tarda unos 11 minutos] → Entre commits se ejecuta `tests/asistente/test_bot.py`, la parte rápida que importa. La suite completa se ejecuta al final, en segundo plano.

## Migration Plan

1. Rama `dividir-conversacion-asistente` desde `main`.
2. Caracterización (decisión 3) y movimiento (decisión 4), con la suite en verde en cada commit.
3. Unir a `main` con la confirmación del dueño.
4. Desplegar con `git pull --ff-only` y reiniciar `buscador-asistente`. Después, prueba manual corta en el bot: `/start`, un ⚡, un botón de la card y `/estado`.
5. Vuelta atrás: `git revert` del merge. No hay datos, esquemas ni configuración que migrar.
