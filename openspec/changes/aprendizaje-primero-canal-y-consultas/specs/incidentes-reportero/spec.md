# Spec Delta

## ADDED Requirements

### Requirement: Incidente del clasificador IA
El detector MUST abrir el incidente `ia:clasificador` en cualquiera de estos casos:
- el saldo de DeepSeek está por debajo de `ia.saldo_minimo_usd`;
- se alcanzó el tope diario de llamadas del clasificador;
- `incidentes.corridas_ia_fallida` corridas seguidas (2 por defecto) tuvieron dudosas y ninguna respuesta válida;
- venció una dudosa sin clasificar.

El aviso MUST ir al chat de administración y decir la causa, cuántas dudosas siguen pendientes y cuántas vencieron.

#### Scenario: Saldo bajo
- **WHEN** una corrida tiene dudosas y el saldo de DeepSeek es de 0,40 USD con un mínimo de 1,00
- **THEN** se abre `ia:clasificador` con la causa «saldo bajo» y el aviso va al chat de administración

#### Scenario: Corridas sin respuesta
- **WHEN** dos corridas seguidas mandan dudosas a la IA y no reciben ninguna respuesta válida
- **THEN** se abre `ia:clasificador` con el motivo del último fallo

### Requirement: Cierre del incidente del clasificador
El incidente `ia:clasificador` MUST cerrarse en la primera corrida en que el clasificador recibe una respuesta válida y el saldo supera el mínimo. Al cerrarse, MUST avisarse con cuántas dudosas pendientes se clasificaron.

#### Scenario: Recarga de saldo
- **WHEN** el administrador recarga el saldo y la corrida siguiente clasifica 12 dudosas pendientes
- **THEN** el incidente se cierra con un aviso de que se clasificaron 12 dudosas pendientes
