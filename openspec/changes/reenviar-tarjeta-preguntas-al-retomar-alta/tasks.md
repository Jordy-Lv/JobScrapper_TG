## 1. Textos y reenvío

- [ ] 1.1 Añadir en `textos.py` el aviso de registro a medias, con y sin vacante guardada
- [ ] 1.2 `_pintar_preguntas(nuevo=True)`: enviar la tarjeta nueva, borrar la antigua (mejor esfuerzo) y guardar el nuevo `mensaje_id`
- [ ] 1.3 `_reanudar_preguntas` y `_continuar_alta` aceptan `reenviar`; `al_iniciar` lo activa en la rama `ALTA` y envía el aviso antes de la tarjeta

## 2. Pruebas

- [ ] 2.1 `/start v_<id>` con alta en `faltantes:0` y tarjeta previa: llegan aviso y tarjeta nueva, se borra la antigua y `vacante_pendiente` queda guardada
- [ ] 2.2 `/start` sin vacante: aviso sin mención de vacante, y fallo al borrar la tarjeta antigua no rompe el flujo
- [ ] 2.3 Responder una pregunta desde la tarjeta sigue editando en su sitio
- [ ] 2.4 Correr la suite (`.venv/Scripts/python -m pytest`) y `ruff`; solo deben fallar las 3 pruebas propias de Windows

## 3. Despliegue

- [ ] 3.1 👤 Desplegar en Fedora (`git pull --ff-only` y reiniciar `buscador-asistente`) y probar el botón de una oferta del grupo
