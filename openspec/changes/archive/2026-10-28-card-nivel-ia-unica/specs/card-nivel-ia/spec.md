## ADDED Requirements

### Requirement: Card única del nivel de IA
El asistente SHALL mostrar el nivel de IA en un solo mensaje. Al elegir un nivel, el mismo mensaje MUST
actualizarse (nivel marcado y consumo) sin enviar otro. Un nuevo `/ia` MUST borrar la card anterior si sigue
en pantalla, de modo que el usuario nunca vea dos cards del nivel a la vez.

#### Scenario: Elegir un nivel
- **WHEN** el usuario abre `/ia` y toca «Máximo»
- **THEN** el mismo mensaje pasa a marcar «Máximo» y no llega ningún mensaje nuevo

#### Scenario: Abrir /ia dos veces
- **WHEN** el usuario escribe `/ia` y, sin cerrarla, vuelve a escribir `/ia`
- **THEN** la primera card se borra y solo queda la nueva

### Requirement: Cerrar la card del nivel de IA
La card SHALL llevar un botón «Cerrar» que la borra de inmediato.

#### Scenario: Cerrar
- **WHEN** el usuario toca «Cerrar» en la card
- **THEN** el mensaje desaparece del chat

### Requirement: Borrado automático de la card del nivel de IA
La card SHALL borrarse sola: poco después de elegir un nivel y, si nadie la toca, tras un tiempo de lectura.
El borrado MUST sobrevivir a un reinicio del servicio. Elegir un nivel MUST reiniciar el plazo corto.

#### Scenario: Elegir y esperar
- **WHEN** el usuario elige un nivel y no toca nada más
- **THEN** la card se borra a los pocos segundos y el nivel queda guardado

#### Scenario: Nadie la toca
- **WHEN** el usuario abre `/ia` y no elige nada
- **THEN** la card se borra al cumplirse el tiempo de lectura
