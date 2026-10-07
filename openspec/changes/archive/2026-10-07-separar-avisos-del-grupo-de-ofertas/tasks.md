## 1. Configuración

- [x] 1.1 Añadir `telegram_chat_admin` a `Secretos` y leer `TELEGRAM_CHAT_ADMIN` en `cargar_secretos` (opcional) en `buscador_vacantes/config.py`
- [x] 1.2 Documentar la variable en `.env.example`, `deploy/INSTALAR.md` y README

## 2. Enrutamiento

- [x] 2.1 Añadir `_chat_admin()` en `corrida.py` (prueba → admin → respaldo al grupo de ofertas con advertencia) y usarlo en `_incidentes`
- [x] 2.2 Usar el mismo destino en `_resumen` de `corrida.py`
- [x] 2.3 Confirmar que `asistente/` no envía mensajes operativos al grupo de ofertas

## 3. Pruebas

- [x] 3.1 `tests/test_config.py`: lectura opcional de `TELEGRAM_CHAT_ADMIN`
- [x] 3.2 Pruebas de corrida/resumen: ofertas al grupo, incidentes y resumen al admin, respaldo con variable ausente y modo prueba
- [x] 3.3 Ejecutar la suite completa y `ruff`

## 4. Despliegue (👤 del dueño)

- [x] 4.1 Crear el grupo, añadir el bot y poner `TELEGRAM_CHAT_ADMIN` en el `.env` del servidor Fedora
