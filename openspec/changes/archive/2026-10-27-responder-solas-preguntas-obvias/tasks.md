## 1. Pruebas que fallan primero

- [x] 1.1 🟢 En `tests/asistente/test_respuestas.py`, cambiar `test_opciones_sin_dato_conocido_van_al_redactor_para_elegir` a «¿Prefieres trabajo en equipo?» (Si/No) y agregar: (a) «¿Te animas a dar el siguiente paso en tu camino laboral y participar en este proceso que podría abrirte nuevas oportunidades?» → opción «Si», origen `perfil`, sin llamadas a la IA; (b) «¿Confirmas tu participación en el proceso?» sin cliente de IA → «Si»; (c) lo aprendido («No») gana a la regla; (d) «¿Autorizas el tratamiento de tus datos personales para participar en este proceso?» → `falta`; (e) «¿Tienes experiencia previa en soporte técnico?» no la resuelve la regla; (f) pregunta con una sola opción, o sin negativa, no aplica. Verificar que (a), (b) y (c) fallan con el código actual.

## 2. Regla en el resolvedor

- [x] 2.1 🟡 `buscador_vacantes/asistente/respuestas.py`: patrón de confirmación de interés (fórmula + referencia al proceso, descartando negaciones y condicionales) y función `confirma_interes(norma, opciones)`; en `resolver()` llamarla justo después del chequeo de `es_consentimiento` y devolver `Respuesta(opcion=<índice de la afirmativa>, origen=Origen.PERFIL)`. Verificar con 1.1 en verde y `tests/asistente/test_respuestas.py` y `test_nucleo.py` completos.
- [x] 2.2 🟢 Correr la suite completa (`uv run pytest`) y `uv run ruff check` / `ruff format --check`.

## 3. Despliegue

- [ ] 3.1 👤 `git pull` en el Fedora y reiniciar el servicio del asistente; comprobar en la próxima postulación de Magneto que las preguntas de ánimo y de confirmación ya no salen en la card.
