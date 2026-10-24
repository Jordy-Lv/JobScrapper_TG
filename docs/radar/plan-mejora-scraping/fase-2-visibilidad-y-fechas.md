# Fase 2: visibilidad por área y fecha transparente

| | |
|---|---|
| **Dificultad** | 🟡 media: modelo, filtros, formato, estado y pruebas de formato |
| **Change de OpenSpec** | `visibilidad-area-y-fecha` (nuevo; reemplaza el bloque 5 «destacadas» del change abierto) |
| **Atiende** | puntos 5 (visibilidad de las áreas foco) y 6 (fecha más específica) |
| **Depende de** | puede ir en paralelo con la [fase 1](fase-1-aprendizaje-primero.md), pero usa su tarea E6 (el área de las prácticas). Si la fase 1 no ha llegado a E6, esta fase la implementa. |

## Objetivo

1. Que las vacantes de **bases de datos, programación, infraestructura y QA** se vean primero y se distingan de un vistazo. Las demás de TI (soporte, datos, ciberseguridad, otros) se siguen publicando.
2. Que cada tarjeta diga **cuándo se publicó la vacante**, con la precisión que da el portal y sin inventar horas.

## Límite técnico: Telegram

Telegram **no permite cambiar el tamaño de letra** en los mensajes de un bot. El modo HTML solo acepta `<b>`, `<i>`, `<u>`, `<s>`, `<code>`, `<pre>`, `<blockquote>`, `<tg-spoiler>` y `<a>`. La visibilidad se logra con cuatro recursos:

- la **posición** (primero en el mensaje);
- **negrita y MAYÚSCULAS** en la etiqueta del área;
- el **bloque citado** (`<blockquote>`, la barra lateral de color de Telegram);
- un **emoji por área**, siempre el mismo, para reconocerla sin leer.

## Parte A: áreas foco

### Datos

- La categoría actual se mantiene para las secciones.
- Se usa un **área** independiente: es la tarea E6 de la fase 1, guardada en `vistas.area`. Así, un «Aprendiz SENA de desarrollo» es categoría `practicas`, pero área `desarrollo`, y se resalta.
- Detección dedicada de las 4 áreas foco, con este orden de prioridad: bases de datos → QA → programación → infraestructura. Se evita así que «datos» gane antes que «bases de datos», como pasa hoy con el orden de `filtros.areas`.
- Configurable en `config.yaml`:

```yaml
publicacion:
  areas_foco:
    activo: true
    areas: [bases_datos, qa, desarrollo, infraestructura]
    etiquetas:
      bases_datos: "🗄️ BASES DE DATOS"
      desarrollo: "💻 PROGRAMACIÓN"
      infraestructura: "🌐 INFRAESTRUCTURA"
      qa: "🧪 QA / TESTING"
```

### Formato propuesto del mensaje

```text
🔔 7 vacantes nuevas · 🎯 3 de tu perfil

🎯 <b>MATCH CON TU PERFIL</b>

┃ 🗄️ <b>BASES DE DATOS</b> · 🎓 Contrato de aprendizaje
┃ <b><a href="…">Aprendiz SENA Administración de Bases de Datos</a></b>
┃ 🏢 Empresa A · 📍 Remota (Colombia)
┃ 📅 Publicada: vie 24 oct, 10:15 (hace 3 h)
┃ 🔎 Magneto

┃ 💻 <b>PROGRAMACIÓN</b> · 🌱 Sin experiencia
┃ <b><a href="…">Desarrollador Python – Primer empleo</a></b>
┃ 🏢 Empresa B · 📍 Cartagena (Híbrido)
┃ 📅 Publicada: jue 23 oct (ayer)
┃ 🔎 Computrabajo

┃ 🧪 <b>QA / TESTING</b> · 🎓 Práctica profesional
┃ …

━━━━━━━━━━━━━━
🎓 <b>OTRAS VACANTES DE TI</b>
• <a href="…">Practicante de Soporte TI</a> — Empresa C · Cartagena · 📅 hoy 09:40
• <a href="…">Aprendiz Ciberseguridad</a> — Empresa D · Remota · 📅 22 oct
```

(`┃` representa el `<blockquote>` de Telegram.)

- **Bloque «🎯 MATCH CON TU PERFIL»:** va primero, con la tarjeta completa dentro de `<blockquote>`. La primera línea lleva la etiqueta del área en negrita y mayúsculas y la insignia de nivel: 🎓 práctica o aprendizaje, 🌱 sin experiencia.
- **Resto:** formato compacto de una línea, con el título como enlace, empresa, lugar y fecha.
- **Encabezado:** cuenta las de perfil.
- **Corte a 4.096:** el título del bloque se repite al partir el mensaje y una tarjeta nunca se corta. `componer` (`radar/formato.py:110`) ya mide por bloque.
- **Si no hay vacantes de perfil,** el mensaje empieza directamente con «Otras vacantes de TI».

> El dueño aprueba o ajusta esta maqueta en el chat de prueba (tarea 👤) antes del despliegue. Los textos y emojis quedan en `config.yaml`, para cambiarlos sin tocar código.

## Parte B: fecha transparente

### Qué da cada fuente

| Fuente | Lo que da | Cómo se muestra |
|---|---|---|
| GetOnBoard, Magneto | fecha y hora exactas | 📅 Publicada: vie 24 oct, 10:15 (hace 3 h) |
| LinkedIn con «Hace N horas» | hora aproximada | 📅 Publicada: hoy, hace ~9 h |
| LinkedIn con solo `datetime`, SPE | solo el día | 📅 Publicada: jue 23 oct (ayer) |
| Computrabajo, elempleo («Ayer», «Hace 2 días») | día relativo | 📅 Publicada: jue 23 oct (ayer), sin hora |
| Sin fecha | nada | 📅 El portal no indica fecha · vista por primera vez hoy 09:12 |

### Cambios

- `comun/modelo.py`: `Vacante` gana `publicada_precision`, con los valores `exacta`, `aproximada`, `dia` o `relativa`. Va también en `vacante_a_json`.
- Cada fuente fija la precisión al interpretar su fecha (`fuentes/*.py`). `comun/fechas.py:interpretar_fecha` devuelve la precisión junto a la fecha; «ayer» deja de inventar la hora del scraping.
- Nueva función `fechas.fecha_publicacion(vacante, ahora)`, con nombres de días y meses en español propios: no depende del *locale* del servidor. Reemplaza a `fecha_relativa` (`comun/fechas.py:121`) en la tarjeta.
- `Estado.registrar_vista` guarda `publicada` (más la precisión), `area` y `destacada` al publicar. Las columnas ya existen en el esquema 4, salvo la precisión, que va en una migración nueva.

## Tareas

1. 🟡 `Vacante.publicada_precision`, la precisión en `interpretar_fecha` y en cada fuente; pruebas por fuente con los fixtures de `tests/fixtures`.
2. 🟢 `fechas.fecha_publicacion`, con pruebas de los cinco casos de la tabla, incluido el cambio de día en Bogotá.
3. 🟡 Área foco: configuración `publicacion.areas_foco`, detección dedicada (o la E6 de la fase 1) y `Filtros.area_foco(vacante)`.
4. 🟡 `formato.py`: bloque de perfil con `<blockquote>`, formato compacto, encabezado con conteo y corte a 4.096. Agregar `blockquote` a `Verificador.PERMITIDAS` en `tests/radar/test_formato.py`.
5. 🟢 `registrar_vista` con `publicada`, la precisión, `area` y `destacada`; la migración del esquema; las pruebas en `test_estado.py` y `test_publicacion.py`.
6. 👤 Corrida con `--chat-prueba` que mezcle vacantes de perfil y normales. El dueño aprueba el formato.

## Criterios de aceptación

- [ ] Toda tarjeta publicada tiene una línea 📅 con fecha, o con el aviso explícito de que el portal no la da.
- [ ] Ninguna tarjeta muestra una hora que el portal no dio.
- [ ] Toda vacante de las 4 áreas foco, incluidas las prácticas, aparece en el bloque «🎯 MATCH CON TU PERFIL» con su etiqueta.
- [ ] Ningún mensaje pasa de 4.096 unidades UTF-16; se prueba con un lote de 30 vacantes de perfil.
- [ ] `vistas.publicada` y `vistas.area` se llenan en cada envío.
- [ ] El dueño aprobó el formato en el chat de prueba.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El `<blockquote>` hace los mensajes más largos y se parten más. | Formato compacto para el resto, y medir con un lote real en el chat de prueba. |
| Si casi todo es «de perfil», el resalte pierde valor. | Medirlo en 3 días. Si pasa del 60 %, restringir a área foco **en el título**. |
| El asistente lee `vistas` y puede romperse con columnas nuevas. | La migración solo agrega columnas; correr también `tests/asistente`. |

## Sesión recomendada

**Sesión nueva** si la fase 1 ya cargó mucho contexto. Mensaje listo para pegar:

> Ejecuta la fase 2 de `docs/radar/plan-mejora-scraping/fase-2-visibilidad-y-fechas.md`: crea con `/opsx:propose` el change `visibilidad-area-y-fecha` (áreas foco con bloque «MATCH CON TU PERFIL» y fecha con precisión por fuente) y aplícalo hasta la tarea 5. La 6 es del dueño.
