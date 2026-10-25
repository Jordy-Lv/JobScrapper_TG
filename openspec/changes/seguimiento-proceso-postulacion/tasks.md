## 1. Modelo de datos

- [ ] 1.1 🟡 Agregar en `datos.py` las tablas `procesos`, `proceso_eventos` y `recordatorios` (decisión 1 del diseño), subir `ESQUEMA_VERSION` a 5 y escribir `_a_v5` con la migración: procesos para `enviada`/`ya_postulada` y para `respaldo` con `seguimiento = 'postulada'`, `archivado` para `descartada` y eventos de usuario para `entrevista`/`rechazada`. Verificar con pruebas en `tests/asistente/test_datos.py`: base nueva, base v4 con postulaciones de cada caso y doble arranque sin duplicar.
- [ ] 1.2 🟢 Verificar que la baja y el borrado por inactividad dejan vacías las tres tablas para ese usuario (`ON DELETE CASCADE`), incluidos los procesos externos. Verificar con una prueba en `tests/asistente/test_usuarios.py`.

## 2. Núcleo de procesos (`procesos.py`)

- [ ] 2.1 🟡 Implementar la función pura de estado derivado (rangos, cierres y reapertura, eventos `media` sin confirmar). Verificar con una prueba de tabla de casos en `tests/asistente/test_procesos.py` que cubra cada escenario del requisito «Eventos con origen y seguridad».
- [ ] 2.2 🟡 Implementar `Procesos.abrir` (desde una postulación o externo, idempotente) y `Procesos.registrar` (dedupe por clave, recálculo, resultado de aviso según la prioridad). Verificar con pruebas de apertura repetida, evento repetido y un evento `media` que pide confirmación.
- [ ] 2.3 🟡 Abrir el proceso cuando la postulación termina `enviada`/`ya_postulada` (donde `cola`/`nucleo` registran el resultado) y cuando se toca «Ya me postulé». Verificar con pruebas en `test_nucleo.py` y `test_bot.py`.

## 3. Fechas, `.ics` y recordatorios

- [ ] 3.1 🟡 Escribir el parser de fechas en español (decisión 4) con fechas siempre futuras en America/Bogota. Verificar con una prueba de tabla: «martes 10am», «mañana 9», «20/10 3:30 pm», «15 de noviembre 2 p. m.», «hoy 8» después de las 8 y textos inválidos.
- [ ] 3.2 🟢 Escribir `ics.py` (VTIMEZONE fijo, UID estable, SEQUENCE, VALARM, escape y plegado). Verificar con una prueba que valide la estructura y, si está disponible en el entorno de pruebas, que `icalendar` lo lea sin errores.
- [ ] 3.3 🟡 Programar, cancelar y reprogramar recordatorios de entrevista (24 h, 2 h, 15 min) y los `diferido` por silencio, con su envío en `Conversacion.recordatorios` cada 60 s. Verificar con pruebas de reloj fijo: envío a tiempo, reprogramación, cancelación al cerrar y omisión del vencido tras una caída.

## 4. Card y conversación

- [ ] 4.1 🟡 Card confirmada: estado del proceso, hasta tres eventos con su ícono de origen, la próxima entrevista y la fila «Me contactaron», «Entrevista», «Me descartaron», «Más», con la vista «Más». Verificar con pruebas en `tests/asistente/test_tarjeta_postulacion.py` (✓ en el avance vigente, máximo 3 por fila, límite de 4000 caracteres).
- [ ] 4.2 🟡 Callbacks `pav`/`pmas` y la fase `FECHA` (texto que se borra, confirmación «Confirmar»/«Corregir», enlace o lugar opcional, `.ics` al confirmar), y la compatibilidad de `seg` con `entrevista`/`rechazada`. Verificar con pruebas en `test_bot.py` para cada escenario del requisito «Registro manual de avances» y el delta de la card.
- [ ] 4.3 🟡 Repintar la card con los eventos de otras fuentes (editar o reenviar si ya no se puede editar) y enviar los mensajes urgentes con sonido. Verificar con una prueba que registra un evento `portal` y uno `correo` falsos y revisa las llamadas a la salida de Telegram.
- [ ] 4.4 🟢 Agregar `/procesos` (orden por urgencia) y cambiar `/historial` para mostrar el estado del proceso. Registrar el comando en la lista del bot. Verificar con pruebas de orden y del caso sin procesos.

## 5. Reglas y tareas periódicas

- [ ] 5.1 🟡 Implementar `aplicar_reglas` (seguimiento con borrador, vacante cerrada, `sin_respuesta`, «¿Cómo te fue?») con aviso único por regla en `avisos_json`, y llamarla desde `_tareas_diarias`. Verificar con pruebas de reloj fijo para cada regla y su no repetición.
- [ ] 5.2 🟡 Revisión de vacantes con proceso abierto vía `Detalles.obtener`, con tope por corrida e intervalo. Verificar con `respx`: una oferta cerrada genera el evento `vacante` y una abierta no genera nada.
- [ ] 5.3 🟡 Resumen semanal en el día y la hora configurados (una vez por semana, guardado en `kv`). Verificar con pruebas de contenido y de que un usuario sin procesos no lo recibe.
- [ ] 5.4 🟢 Horas de silencio aplicadas a los avisos normales y a las sugerencias. Verificar con una prueba a las 22:00 que difiere y a las 23:00 un urgente que pasa.

## 6. Configuración, IA y textos

- [ ] 6.1 🟢 Sección `asistente.seguimiento` en `config.yaml` y `comun/config.py` (días, recordatorios, silencio, resumen, topes), con valores por defecto validados. Verificar con la prueba de carga de configuración.
- [ ] 6.2 🟡 Tareas de IA opcionales `interpretar_fecha` y `redactar_seguimiento` con caída a la configuración de `responder` (decisión 9). Verificar con pruebas de configuración y con un cliente IA falso.
- [ ] 6.3 🟢 Textos en `textos.py`, el párrafo de privacidad en `config.yaml` y la sección «Seguimiento de tus procesos» en `docs/asistente/guia-usuario.md`. Verificar leyendo el texto y con la prueba de la página de privacidad.

## 7. Cierre local

- [ ] 7.1 🔴 Correr la suite completa y `ruff check` / `ruff format --check` en segundo plano, sin tocar archivos mientras corre. Verificar con todo en verde. Recomendar sesión nueva antes de empezarla si el contexto ya está cargado.
- [ ] 7.2 🟢 Hacer commit solo de los archivos de este change, en español y sin atribuciones a la IA. Verificar con `git show --stat` y `git log -1 --format=%B`.

## 8. Despliegue y prueba real

- [ ] 8.1 👤 Copiar `asistente.db` en el Fedora, desplegar (`git pull --ff-only`, reiniciar `buscador-asistente`) y comprobar en el log que la migración a esquema 5 corrió y abrió procesos para las postulaciones existentes. Verificar con `sqlite3 asistente.db "SELECT estado, COUNT(*) FROM procesos GROUP BY 1"`.
- [ ] 8.2 👤 Prueba real en Telegram sobre una postulación ya enviada: «Entrevista» con una fecha de prueba cercana, recibir el `.ics` y abrirlo en el celular, recibir los recordatorios y marcar «Me descartaron» para cerrarla. Verificar que la card, `/procesos` y el calendario reflejan cada paso.
- [ ] 8.3 🟢 Archivar con `/opsx:archive` antes de archivar `leer-procesos-portales`, `correo-seguimiento-reenvio` y `gmail-api-y-calendario`. Verificar con `openspec validate` y `openspec list`.
