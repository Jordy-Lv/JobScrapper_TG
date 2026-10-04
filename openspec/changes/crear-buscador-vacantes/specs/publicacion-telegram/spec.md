# Spec Delta

## Purpose

Publicar en el canal de Telegram solo las vacantes nuevas, en español, con un formato compacto, legible y sin ruido técnico, que mejora el formato actual de Hermes.

## ADDED Requirements

### Requirement: Envío solo cuando hay vacantes nuevas
El sistema SHALL enviar mensajes de vacantes al canal configurado solo si la corrida produjo al menos una vacante nueva aceptada. Sin vacantes nuevas MUST NOT enviar nada, ni siquiera el banner.

#### Scenario: Corrida sin novedades
- **WHEN** una corrida no encuentra vacantes nuevas
- **THEN** no se envía ningún mensaje al canal

### Requirement: Formato del mensaje
El sistema SHALL formatear cada envío en HTML de Telegram así:
- un encabezado con la cantidad: "🔔 N vacantes nuevas" (en singular cuando N es 1);
- vacantes agrupadas por categoría, cada grupo con su título en este orden: "🎓 PRÁCTICAS Y APRENDIZAJE", "💻 DESARROLLO JUNIOR", "🚀 INFRAESTRUCTURA / DEVOPS / CLOUD JUNIOR", "🗄 BASES DE DATOS JUNIOR", "🛠 SOPORTE IT JUNIOR", "📊 DATOS Y ANALÍTICA JUNIOR", "🧪 QA / TESTING JUNIOR", "🔐 CIBERSEGURIDAD JUNIOR" y "🧩 OTROS TI JUNIOR". Las categorías vacías no se muestran;
- dentro de cada categoría, las más recientes primero;
- por ficha: título en negrita como enlace a la oferta; una línea "🏢 empresa · 📍 ubicación (modalidad)"; una línea "💰 salario" solo si hay salario; y una línea "🔎 fuente · 🕒 fecha relativa", omitiendo la fecha si no se conoce.

Las fechas relativas MUST expresarse como "hoy", "ayer" o "hace N días" en hora de Colombia. Los mensajes MUST NOT incluir texto técnico de cron, ids de job ni texto en inglés generado por el sistema.

#### Scenario: Ficha sin salario
- **WHEN** una vacante no tiene salario
- **THEN** su ficha tiene 3 líneas y no incluye la línea 💰

#### Scenario: Ficha con salario
- **WHEN** una vacante publica "1 SMMLV + auxilio"
- **THEN** su ficha incluye la línea "💰 1 SMMLV + auxilio"

#### Scenario: Una sola vacante
- **WHEN** la corrida tiene 1 vacante nueva
- **THEN** el encabezado dice "🔔 1 vacante nueva"

### Requirement: Escape de caracteres
El sistema MUST escapar `<`, `>` y `&` en todos los campos de texto provenientes de las fuentes antes de componer el HTML, para que títulos como "Desarrollador C++ & .NET <Jr>" se muestren tal cual y no rompan el mensaje.

#### Scenario: Título con caracteres especiales
- **WHEN** el título es "Practicante QA & Testing <remoto>"
- **THEN** Telegram acepta el mensaje y el título se muestra literalmente

### Requirement: División por límite de tamaño
El sistema SHALL dividir un envío que supere los 4096 caracteres en varios mensajes consecutivos, sin cortar ninguna ficha y repitiendo el título de categoría al inicio de cada mensaje que continúa una categoría.

#### Scenario: Muchas vacantes
- **WHEN** una corrida produce 40 vacantes nuevas
- **THEN** se envían varios mensajes, cada uno de 4096 caracteres o menos, y ninguna ficha queda partida

### Requirement: Opciones de envío
Los mensajes de vacantes SHALL enviarse con la vista previa de enlaces desactivada y con notificación (no hay horario silencioso).

#### Scenario: Envío nocturno
- **WHEN** a las 23:30 hay vacantes nuevas
- **THEN** se envían con notificación normal

### Requirement: Banner configurable
El sistema SHALL soportar tres modos de banner, `diario` (por defecto), `nunca` y `siempre`. En modo `diario`, la imagen del banner se envía antes del primer envío con vacantes de cada día (hora de Colombia), y la fecha del último banner MUST persistir.

#### Scenario: Primer envío del día
- **WHEN** el modo es `diario` y a las 07:00 se hace el primer envío con vacantes del día
- **THEN** se envía primero el banner y luego las vacantes

#### Scenario: Segundo envío del día
- **WHEN** el modo es `diario` y ya se envió el banner hoy
- **THEN** las vacantes se envían sin banner

### Requirement: Confirmación de envío
Una vacante SHALL marcarse como enviada solo cuando Telegram confirme el mensaje que la contiene. Si Telegram rechaza un mensaje, sus vacantes MUST quedar sin marcar para reintentarlas en la siguiente corrida, y el rechazo MUST registrarse para el detector de incidentes.

#### Scenario: Rechazo de Telegram
- **WHEN** Telegram responde con error de parseo a uno de tres mensajes
- **THEN** las vacantes de los otros dos quedan enviadas y las del rechazado se reintentan en la siguiente corrida

### Requirement: Chat de prueba
El sistema SHALL permitir redirigir todos los envíos (vacantes, alertas y resúmenes) a un chat de prueba configurado, sin cambiar el estado de envíos al canal real.

#### Scenario: Envío a chat de prueba
- **WHEN** se ejecuta con la opción de chat de prueba
- **THEN** los mensajes llegan al chat de prueba y ninguna vacante queda marcada como enviada al canal
