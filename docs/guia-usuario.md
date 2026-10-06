# Guía del usuario: asistente de postulación

Tocas **⚡ Postularme** en una vacante del grupo y el sistema hace el resto: abre la vacante con
tu cuenta, llena tus datos, responde las preguntas, usa un CV levemente adaptado a esa oferta,
envía la postulación y te confirma por Telegram qué respondió.

Es solo para miembros del grupo privado **JOBS - PRÁCTICAS/APRENDIZ** (el bot lo comprueba) y es
gratuito. La versión con diagramas está en `docs/guia-asistente-postulacion.pdf`.

## Qué necesitas

| Requisito | Para qué |
|---|---|
| Cuenta de Telegram y ser miembro del grupo | Usar el bot y recibir los avisos |
| Un computador (Windows, macOS o Linux) | Allí funciona la extensión que postula |
| Microsoft Edge (recomendado), Chrome o Brave | Navegador de la extensión |
| Cuenta de Google | Sacar tu clave gratuita de Gemini (la IA) |
| Cuenta en Computrabajo y/o Magneto | Las plataformas donde se postula sola |
| Tu hoja de vida en PDF | El bot la lee para armar tu perfil |

## Instalación paso a paso (una sola vez, unos 10 minutos)

1. **Abre el bot y acepta la autorización de datos.** Toca ⚡ Postularme en cualquier vacante del
   grupo, o busca el bot y pulsa *Iniciar*. Lee la autorización (Ley 1581 de 2012) y pulsa
   *Acepto*.
2. **Consigue tu clave gratuita de Gemini.** Entra a [aistudio.google.com](https://aistudio.google.com)
   con tu cuenta de Google, abre *Get API key* → *Crear clave de API*, copia la clave y pégala en
   el chat del bot. El bot la borra del chat al instante y la guarda cifrada; solo te muestra sus
   últimos 4 caracteres.
3. **Envía tu hoja de vida en PDF.** El bot la lee y te muestra tu perfil por secciones
   (formación, experiencia, proyectos, habilidades, idiomas). Revisa cada una y pulsa
   *Correcto* o *Corregir*; luego confirma los roles y tecnologías que quieres destacar. Tu
   correo, teléfono y documento no se envían a la IA.
4. **Responde el cuestionario base** (unas 10 preguntas, casi todas con botones): aspiración
   salarial, disponibilidad, estudios, inglés, modalidad y ciudades, y si autorizas que se
   actualice tu CV en los portales. Si lo dejas a medias, el bot retoma donde quedaste.
5. **Instala la extensión.**
   - *Edge (recomendado):* abre el enlace de la tienda que te envía el bot → *Obtener* →
     *Agregar extensión*. Se actualiza sola.
   - *Chrome o Brave (carga manual):* descarga el `.zip` que te envía el bot y descomprímelo en
     una carpeta fija; abre `chrome://extensions`, activa *Modo de desarrollador* y pulsa
     *Cargar descomprimida*. Cuando haya versión nueva, el bot te avisa.
   - Fija el ícono de la extensión en la barra para ver su estado.
6. **Vincula tu navegador.** En el bot toca *Vincular mi navegador*: se abre una página que la
   extensión reconoce sola. El bot confirma «Navegador vinculado».
7. **Inicia sesión en Computrabajo y Magneto** en ese mismo navegador, como siempre. La extensión
   lo detecta y el bot te avisa «Computrabajo listo» y «Magneto listo», con el correo de cada
   cuenta para que confirmes que es la tuya.
   - *Si no tienes cuenta:* el bot te da el enlace de registro. La cuenta la creas tú, porque
     requiere tu contraseña y la verificación de tu correo.
   - *Si tu perfil del portal está incompleto:* la extensión lo completa con tu perfil y tu CV.
     Nunca borra lo que ya tienes ni toca tu contraseña o tu correo de acceso.
   - *Tu cuenta queda asociada:* antes de cada postulación se comprueba que la sesión abierta sea
     la de tu correo. Si es otra, no se postula y el bot te avisa.

## Uso diario

- Toca **⚡ Postularme** en la vacante que te interese (puedes hacerlo desde el celular).
- **Mantén tu computador encendido con el navegador abierto** (puede estar minimizado). La
  extensión revisa cada 30 segundos si hay postulaciones pendientes.
- Con el navegador abierto suele tardar menos de 2 minutos. Si estaba apagado, la postulación
  espera en cola; si pasan 24 horas, el bot te envía un paquete listo para copiar.
- Puedes tocar varias vacantes seguidas: se postulan de a una, con pausas. Máximo 15 por día.
- **Modo automático (opcional):** `/automatico 70` postula solo a las vacantes con 70 % o más de
  afinidad con tu perfil. Se desactiva con el mismo comando.

## Cómo se responden las preguntas

Se usa el primer paso que tenga la respuesta: 1) tu perfil y cuestionario; 2) el banco
compartido de preguntas frecuentes; 3) tus respuestas aprendidas de antes; 4) Gemini, solo para
preguntas abiertas y siempre con tus datos reales. Si falta un dato obligatorio, el bot te lo
pregunta una sola vez. El sistema nunca inventa respuestas.

## Tu CV adaptado

Se ajusta levemente a cada vacante: el resumen profesional, el orden de hasta 6 habilidades y
hasta 3 nombres equivalentes (por ejemplo «JS» → «JavaScript»). Nunca cambia tus experiencias,
estudios o fechas, ni agrega habilidades que no tengas. Si el portal usa el CV guardado en tu
perfil, la extensión lo actualiza con la versión de esa vacante antes de postular (solo si lo
autorizaste; puedes cambiarlo en `/perfil`). Ojo: una empresa a la que te postulaste antes podría
ver la versión más reciente.

## Situaciones especiales

| Situación | Qué pasa |
|---|---|
| Vacante de LinkedIn, elempleo, GetOnBoard u otra plataforma | No se postula sola: recibes un paquete listo para copiar (CV adaptado, carta, respuestas y enlace) |
| Aparece un captcha o verificación | La extensión se detiene y te muestra la pestaña; al completarla, sigue sola. Nunca se evaden captchas |
| Se cerró tu sesión en el portal | El bot te avisa «Inicia sesión en…» y lo pendiente se retoma solo |
| La vacante está cerrada o ya te habías postulado | Se te informa y no se envía nada |
| El portal cambió su página | Se detiene sin enviar, recibes el paquete para copiar y el administrador lo corrige |
| Cerraste el navegador a mitad de camino | Si no se había enviado, se reintenta; si ya se pulsó enviar, el bot te pide verificar en «Mis postulaciones» (nunca se envía dos veces) |
| No tienes clave de Gemini o se agotó la cuota | Se postula con tu CV base y tus respuestas; lo que requiera redacción se te pregunta |
| Hay otra cuenta abierta en el portal | No se postula; el bot te muestra tu correo asociado y el encontrado (parcialmente oculto) |
| Sales del grupo de Telegram | Tu acceso se suspende; si vuelves, se reactiva |

## Comandos del bot

| Comando | Para qué sirve |
|---|---|
| `/estado` | Navegador en línea, estado y correo de tu cuenta en cada plataforma y postulaciones de hoy |
| `/historial` | Tus postulaciones con su estado y fecha |
| `/detalle n` | Pasos, preguntas, respuestas y CV usado en una postulación |
| `/perfil` | Ver y editar tu perfil y la autorización para actualizar tu CV en los portales |
| `/cuestionario` | Cambiar tus respuestas del cuestionario base |
| `/cv` | Descargar tu CV base en PDF |
| `/clave` | Cambiar o borrar tu clave de Gemini |
| `/vincular` · `/navegadores` | Vincular un navegador, o ver y revocar los vinculados |
| `/automatico [umbral]` | Activar o desactivar la postulación automática por afinidad |
| `/pausa` | Pausar temporalmente tus postulaciones |
| `/borrarme` | Borrar todos tus datos de forma definitiva |

En cada postulación hay botones para marcar entrevista, rechazo u oferta y llevar tu seguimiento.

## Privacidad y seguridad

- Nadie recibe tu contraseña: la extensión usa la sesión que ya tienes abierta, y el servidor
  nunca recibe contraseñas ni sesiones.
- Las postulaciones salen de tu propia conexión, como si las hicieras tú.
- Tu clave de Gemini se guarda cifrada. Tu documento, correo y teléfono nunca se envían a la IA
  (en el plan gratuito, Google puede usar lo enviado para mejorar sus modelos).
- La extensión solo tiene permiso sobre Computrabajo, Magneto y el servidor del asistente.
- Los portales pueden restringir el uso automatizado de las cuentas. Por eso se postula con
  pausas, con tope diario y deteniéndose ante cualquier verificación.
- Con `/borrarme` se elimina todo: perfil, CV, clave, historial y vínculos.

## Preguntas frecuentes

- **¿Tiene costo?** No. La IA usa tu clave gratuita de Gemini y la extensión es gratuita.
- **¿Puedo usarlo solo desde el celular?** Puedes tocar ⚡ Postularme desde el celular, pero la
  postulación la hace la extensión en tu computador, que debe estar encendido con el navegador
  abierto.
- **¿Funciona en Firefox o Safari?** Por ahora no: usa Edge, Chrome o Brave.
- **¿Puede postularme a algo que no quiero?** No. Solo a lo que tocas, o a lo que supera el
  umbral si activaste `/automatico`.
- **¿Cómo sé qué se respondió por mí?** El mensaje de resultado muestra cada pregunta y su
  respuesta; con `/detalle` ves el proceso completo y el CV enviado.
- **¿Puedo usarlo en dos computadores?** Sí, vincula ambos; cada postulación la hace solo uno.
