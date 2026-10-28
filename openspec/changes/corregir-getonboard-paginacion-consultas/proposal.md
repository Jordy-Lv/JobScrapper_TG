## Why

GetOnBoard casi no aporta vacantes al canal. Medido contra su API el 2026-10-28: el catálogo completo tiene ~1.000 ofertas (499 en Chile, 35 en Colombia, solo 4 de Colombia con nivel junior y ninguna sin experiencia), así que el techo real es bajo. Pero además el recolector desperdicia lo poco que hay:

- Las palabras clave son las globales, en frases largas («practicante sistemas», «aprendiz sistemas», «practicante desarrollo de software»). La búsqueda de GetOnBoard exige **todas** las palabras y no admite `OR`, `|` ni comas, así que esas frases devuelven 0 resultados. Con una sola palabra («practicante», «aprendiz», «internship») sí responde.
- `construir_peticion` manda `"page": 1` fijo y la fuente no declara `soporta_paginas`; aunque se configure `paginas_nucleo`, la corrida lo baja a 1 con un aviso. «junior» tiene 3 páginas y solo se lee la primera.

## What Changes

- **Palabras clave propias por fuente**: una fuente puede declarar en `config.yaml` su propio `núcleo` y `cola larga`; si no las declara, sigue usando las globales. Solo GetOnBoard las declara en este change.
- **GetOnBoard con consultas de una sola palabra**: núcleo de prácticas (`practicante`, `aprendiz`, `pasante`, `pasantía`, `trainee`, `internship`) y cola larga de una palabra (`junior`, `soporte`, `sistemas`, `QA`, `datos`, `redes`, `devops`, `ciberseguridad`, `analista`, `desarrollador`).
- **Paginación real en GetOnBoard**: la petición usa la página pedida y la fuente deja de pedir más páginas al llegar a `meta.total_pages`, no según cuántas ofertas sobrevivan al filtro de nivel.
- Ajuste de presupuesto de GetOnBoard: de 5/1/1 a 6/2/2 (presupuesto / palabras del núcleo / páginas del núcleo).
- Pruebas con fixture para la paginación, el corte por `total_pages` y la carga de la configuración.

No cambia el filtro de nivel (`no_experience`, `junior`), ni el descarte de remotos en inglés, ni las palabras clave de las demás fuentes.

## Capabilities

### New Capabilities
- `busqueda-getonboard`: cómo se consulta GetOnBoard (consultas de una palabra, paginación según `total_pages`) y cómo una fuente puede tener palabras clave propias.

### Modified Capabilities

Ninguna. Los requisitos generales de rotación y presupuesto (`busqueda-fuentes`) siguen en los changes `priorizar-practicas-aprendiz` y `aprendizaje-primero-canal-y-consultas`, que aún no están archivados, así que no existe una spec principal que modificar. Por eso este change declara una capacidad nueva y acotada en lugar de un delta sobre ella.

## Impact

- Código: `buscador_vacantes/radar/fuentes/getonboard.py`, `buscador_vacantes/comun/config.py` (modelo `Fuente`), `buscador_vacantes/radar/corrida.py` (`_consultar`).
- Configuración: `config.yaml`, sección `fuentes.getonboard`.
- Pruebas: `tests/radar/test_getonboard.py`, `tests/comun/test_config.py`, y la de corrida que cubre la selección de palabras clave.
- Costo: GetOnBoard pasa de 5 a 6 peticiones por corrida como máximo (~48 más al día, de ~1.100). Es una API pública y la fuente no tiene historial de bloqueos.
- Expectativa: el volumen seguirá siendo de pocas vacantes de Colombia por semana; el cambio recupera lo que hoy se pierde, no lo multiplica.
- Fuera de alcance: `buscador.py --dry-run` no corre en Windows porque `corrida._limitar_tiempo` usa `signal.SIGALRM`; se deja anotado y no se toca aquí.
