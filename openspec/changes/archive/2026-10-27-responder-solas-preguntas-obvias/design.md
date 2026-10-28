## Context

`resolver()` (`respuestas.py`) decide cada pregunta del formulario en este orden: tipo estándar → dato aprendido → consentimiento (siempre a la card) → banco → autorización de trabajo → receta → clasificación con IA. Una pregunta con opciones que no cae en ninguno termina en `_para_redactar` (`redactar=True`) y es la IA, en una sola llamada con las preguntas abiertas, la que elige la opción. Sin IA (`redactar_formulario` devuelve `None`), con nivel Ahorro (no clasifica) o si la IA responde «faltan datos», la pregunta pasa a `falta=True` y se muestra en la card. Las preguntas de ánimo/confirmación de la encuesta de Magneto nunca van a requerir un dato del usuario: la respuesta es «Si» porque ya está postulando.

## Goals / Non-Goals

**Goals:**
- Responder «Si» a las preguntas de confirmación de interés o participación sin IA y en cualquier nivel.
- No tocar el camino de consentimientos ni lo que el usuario ya respondió.

**Non-Goals:**
- Responder solas otras preguntas de Sí/No (experiencia, disponibilidad, preferencias): siguen con IA o card.
- Cambiar la extensión, `magneto.json` o el banco de preguntas.

## Decisions

1. **Regla de patrones, no IA.** Un patrón normalizado (sin tildes, minúsculas, con `normalizar_pregunta`) exige dos cosas a la vez: fórmula de confirmación/interés (`te animas`, `confirmas`, `estas interesad[oa]`, `deseas|quieres (continuar|seguir|participar)`, `interes`) y referencia al proceso (`proceso|vacante|postulacion|oferta|participacion|aplicacion`). Con una sola de las dos no aplica; así «¿Tienes experiencia…?» o «¿Quieres trabajar en horario nocturno?» quedan fuera. Alternativa descartada: pedirle a la IA un campo «obvia» en la clasificación; no funciona sin IA, que es justo el caso que falla.
2. **Posición en `resolver()`: justo después del chequeo de consentimiento y antes del banco.** Así lo aprendido manda y un consentimiento nunca se contesta. Antes del banco evita que una entrada `redactar` creada por la IA desvíe la pregunta al redactor.
3. **Opción afirmativa con `elegir_opcion("si", opciones)`.** Reutiliza el reconocimiento existente de Si/Sí/Yes. Solo aplica si además hay una opción negativa (`elegir_opcion("no", opciones)`) distinta; una pregunta con una única opción no es un Sí/No.
4. **Origen `Origen.PERFIL`.** Evita un origen nuevo y que el resumen «Tus respuestas» necesite un icono distinto; los datos del perfil ya se muestran sin 🤖 ni 💬 especiales. No se guarda en el banco ni como dato aprendido: la regla se vuelve a evaluar cada vez y no ensucia lo aprendido.
5. **Pregunta con negación o condición.** Si la norma contiene «no te», «sin», «si no» o «en caso de» se descarta la regla para no responder afirmativamente algo condicionado; ante la duda, la pregunta sigue al camino de siempre.

## Risks / Trade-offs

- [Falso positivo: una pregunta con fórmula de interés que en realidad condiciona algo] → exigir las dos condiciones, descartar negaciones y cubrir con pruebas; el usuario puede corregir en la revisión de respuestas.
- [El usuario realmente no quiere participar] → mismo que hoy con la IA, que elegiría «Si»; quien no quiere postular cancela la postulación.
- [Cambio de comportamiento de una prueba existente] → `test_opciones_sin_dato_conocido_van_al_redactor_para_elegir` usa justo esta pregunta; se cambia a una pregunta de Sí/No que no sea de confirmación («¿Prefieres trabajo en equipo?»).
