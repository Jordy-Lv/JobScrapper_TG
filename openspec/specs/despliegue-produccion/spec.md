# despliegue-produccion Specification

## Purpose
Definir las condiciones para integrar la rama del asistente en `main` y desplegarla en producción sin romper el buscador que ya corre.

## Requirements

### Requirement: Integración sin pérdida de cambios
La integración de `asistente-postulacion-telegram` en `main` SHALL conservar los commits de ambas ramas y el contenido de ambos lados en cada conflicto.

#### Scenario: Conflicto de adiciones en pruebas o README
- **WHEN** ambos lados añaden contenido distinto en la misma zona de `README.md` o de un archivo de pruebas
- **THEN** el resultado conserva ambos contenidos y los imports combinados resuelven todos los nombres usados

### Requirement: Suite en verde antes de integrar
El resultado del merge SHALL pasar la suite de pruebas completa antes de integrarse a `main`.

#### Scenario: Suite con fallos
- **WHEN** la suite falla sobre el resultado del merge
- **THEN** no se integra a `main` y se informa al dueño de las pruebas que fallan

### Requirement: Variable de administración en producción
Antes de desplegar, el `.env` de producción SHALL definir `TELEGRAM_CHAT_ADMIN` con un valor no vacío.

#### Scenario: Variable ausente
- **WHEN** el `.env` del servidor no tiene `TELEGRAM_CHAT_ADMIN`
- **THEN** el despliegue no avanza hasta que el dueño la añada, y no se imprime ningún valor secreto en los informes

### Requirement: Confirmación del dueño en pasos externos
El merge a `main`, el push y el despliegue SHALL ejecutarse solo tras la confirmación explícita del dueño para cada paso.

#### Scenario: Merge listo
- **WHEN** el merge de prueba está en verde
- **THEN** se presenta el resultado y se espera la confirmación antes de integrarlo a `main`
