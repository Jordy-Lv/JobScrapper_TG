## 1. Cabecera con plataforma

- [x] 1.1 🟢 Agregar en `textos.py` una función que una empresa y plataforma en «Empresa · Plataforma» (solo la plataforma si no hay empresa, nada si no hay ninguna; escapada). Verificar con pruebas de las cuatro combinaciones.
- [x] 1.2 🟢 Usarla en `_cabecera` de `tarjeta_postulacion.py` y en `resumen_postulacion.tarjeta` (confirmada e incierta). Verificar con pruebas de la card en cola, progreso, pregunta, bloqueo, cancelada, cerrada, confirmada e incierta que la línea aparece, y con plataforma `None` que no aparece.

## 2. Pruebas existentes y cierre

- [x] 2.1 🟡 Actualizar las pruebas que comparan la cabecera exacta y correr `pytest tests/asistente` en verde.
- [ ] 2.2 👤 Del dueño: tras desplegar, postular a una vacante y confirmar en Telegram que la plataforma se ve de la cola a la confirmación.
