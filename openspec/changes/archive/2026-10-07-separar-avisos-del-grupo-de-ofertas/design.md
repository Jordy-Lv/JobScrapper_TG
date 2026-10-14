## Context

`corrida.py` usa un único destino (`_chat_destino`) para ofertas, avisos del reportero y resumen diario (`_resumen` elige el chat por su cuenta). El asistente no escribe en el grupo de ofertas: solo consulta membresía y avisa al dueño por privado.

## Goals / Non-Goals

**Goals:** separar el destino de ofertas y el de operación; no perder avisos si falta configurar el grupo nuevo.
**Non-Goals:** cambiar el contenido de los mensajes; las respuestas del agente Hermes dentro del grupo (como «Reporte recibido, jefe», que no las emite este código) se silencian en la configuración de Hermes, fuera de este repositorio.

## Decisions

- `Secretos.telegram_chat_admin` opcional, leído de `TELEGRAM_CHAT_ADMIN`.
- `_chat_destino()` queda para ofertas; nuevo `_chat_admin()`: prueba → `telegram_chat_prueba`; si no, `telegram_chat_admin`; si falta, `telegram_chat_id` con `log.warning`.
- `_incidentes` y `_resumen` usan `_chat_admin()`. La simulación ya usa el chat de prueba.
- Alternativa descartada: ponerlo en `config.yaml`; el id es un dato del entorno, como los demás chats, y va en `.env`.

## Risks / Trade-offs

- El bot debe ser miembro del grupo nuevo; si no, Telegram rechaza el envío y el incidente se registra solo en el log. Se documenta en `INSTALAR.md`.
- Si el reportero falla al enviar al grupo admin, no se reintenta hacia el grupo de ofertas, para no reintroducir el ruido.
