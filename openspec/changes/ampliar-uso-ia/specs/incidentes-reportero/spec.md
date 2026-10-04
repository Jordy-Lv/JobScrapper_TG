# Spec Delta

## MODIFIED Requirements

### Requirement: Presupuesto de IA y medición de consumo
El sistema SHALL limitar las llamadas del Reportero al máximo diario configurado (20 por defecto), consultar el saldo de DeepSeek antes de cada llamada y registrar los tokens de entrada y salida de cada llamada de IA (reportero, clasificador y resumen).

#### Scenario: Tope diario alcanzado
- **WHEN** ya se hicieron 20 llamadas del Reportero hoy y se abre un incidente nuevo
- **THEN** se envía la alerta plana con el motivo "tope diario alcanzado"
