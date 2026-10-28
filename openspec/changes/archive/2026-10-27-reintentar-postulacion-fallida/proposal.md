## Por qué

Una postulación en elempleo terminó `fallida` con el motivo «la página de la vacante no cargó» (no se pulsó ningún envío) y la card mostró «el portal rechazó el envío», que es falso, y solo ofrecía «Pegar preguntas». El usuario no podía reintentar y el fallo era transitorio: bastaba volver a abrir la página.

## Qué cambia

- La extensión reintenta abrir la página de la vacante (hasta 3 intentos con pausa corta) antes de dar la postulación por fallida, para que salga a la primera.
- La card de una postulación `fallida` explica la causa real («la página de la vacante no cargó») y no culpa al portal.
- La card de `fallida` trae el botón **Reintentar**, que la vuelve a la cola (la cola ya la permite: antes de llenar nada la extensión revisa `ya_postulada`, así que no duplica).

## Impacto

`extension/servicio.js`, `buscador_vacantes/asistente/{textos,tarjeta_postulacion,conversacion}.py` y sus pruebas.
