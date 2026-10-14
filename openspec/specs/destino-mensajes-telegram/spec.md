# destino-mensajes-telegram Specification

## Purpose
TBD - created by archiving change separar-avisos-del-grupo-de-ofertas. Update Purpose after archive.

## Requirements

### Requirement: El grupo de ofertas recibe solo ofertas
El sistema SHALL enviar al chat `TELEGRAM_CHAT_ID` únicamente el banner y los mensajes de vacantes con sus botones, y no SHALL enviarle resúmenes, avisos de incidentes ni mensajes de configuración u operación cuando `TELEGRAM_CHAT_ADMIN` esté definido.

#### Scenario: Corrida con ofertas e incidente
- **WHEN** una corrida publica vacantes y además detecta un incidente
- **THEN** las vacantes van a `TELEGRAM_CHAT_ID` y el aviso del incidente va a `TELEGRAM_CHAT_ADMIN`

#### Scenario: Resumen diario
- **WHEN** se genera el resumen diario
- **THEN** se envía a `TELEGRAM_CHAT_ADMIN` y no a `TELEGRAM_CHAT_ID`

### Requirement: Grupo de administración configurable
El sistema SHALL leer el id del grupo de administración de la variable `TELEGRAM_CHAT_ADMIN` del `.env`, y esa variable MUST ser opcional.

#### Scenario: Variable ausente
- **WHEN** `TELEGRAM_CHAT_ADMIN` no está definida
- **THEN** los resúmenes y avisos van a `TELEGRAM_CHAT_ID` y se registra una advertencia en el log

### Requirement: Modo prueba unificado
En modo prueba el sistema SHALL enviar todos los mensajes, de ofertas y de operación, a `TELEGRAM_CHAT_PRUEBA`.

#### Scenario: Corrida con chat de prueba
- **WHEN** se ejecuta con el chat de prueba y `TELEGRAM_CHAT_ADMIN` está definido
- **THEN** ningún mensaje llega a `TELEGRAM_CHAT_ID` ni a `TELEGRAM_CHAT_ADMIN`
