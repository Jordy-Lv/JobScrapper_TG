# Proposal

## Why

El canal existe para prácticas, pasantías y aprendizaje, pero en el primer día de producción (2026-10-04) solo ~7 de las 122 vacantes enviadas eran prácticas de TI reales. Desde el paso a producción, solo ~138 de ~363 consultas (38 %) buscaron términos de práctica o aprendiz. El grupo núcleo recibe una sola consulta por fuente y por corrida, y mezcla términos de práctica con "junior TI" y "desarrollador junior". Algunas consultas de la cola larga rinden muy poco (SysOps y CloudOps sumaron ~10 resultados en 8 consultas cada una) y otras llenan el canal de técnicos de campo.

Además, cada consulta lee solo la primera página de resultados. En Computrabajo esa página está ordenada por relevancia y no por fecha: para "practicante sistemas" el sitio reporta 70 ofertas de los últimos 3 días y el buscador solo ve 20.

## What Changes

- El grupo **núcleo** pasa a ser exclusivo de prácticas, pasantías y aprendizaje, y gana términos que hoy faltan: "aprendiz ADSO", "aprendiz análisis y desarrollo de software", "practicante ingeniería de sistemas", "práctica profesional ingeniería de sistemas", "aprendiz técnico en sistemas", "pasantía ingeniería de sistemas" y "estudiante últimos semestres ingeniería de sistemas", entre otros. "junior TI" y "desarrollador junior" pasan a la cola larga.
- **Paginación del núcleo:** cada fuente puede leer varias páginas de cada consulta del núcleo (`paginas_nucleo`). Si una página no viene completa, deja de pedir las siguientes. El presupuesto pasa a contar requests (páginas) y `reservado_nucleo` cuenta palabras clave. Computrabajo lee 3 páginas y elempleo 2. Magneto queda en 1 porque ya ordena por fecha de publicación.
- **Presupuestos** (presupuesto / núcleo / páginas):
  - LinkedIn 3/2/1
  - Computrabajo 8/2/3
  - elempleo 5/2/2
  - Magneto 4/2/1
  - GetOnBoard sin cambio (5/1/1)

  En las fuentes sin filtro de nivel nativo, los requests del núcleo son al menos la mitad del presupuesto.
- **Cola larga:**
  - Salen las consultas de bajo rendimiento (SysOps, CloudOps, AWS junior, Azure junior) y las que traen sobre todo técnicos de campo (técnico de redes, telecomunicaciones junior).
  - Entran variantes de práctica por rol (practicante soporte, redes, QA y ciberseguridad).
  - Entran títulos en inglés con nivel explícito: "Software Engineer Intern", "Junior Software Engineer", "Junior Java Developer", "Spring Boot junior", "Junior QA Engineer" y "Junior Data Analyst".
- Paso operativo complementario: reenviar una sola vez las 26 vacantes de TI que la siembra del paso a producción marcó como vistas sin enviarlas.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `busqueda-fuentes`: cambia el requisito "Rotación de palabras clave", con un núcleo exclusivo de prácticas, su cuota mínima de presupuesto y la paginación del núcleo, y el requisito "Presupuesto y ritmo de requests", que ahora cuenta páginas y tiene nuevos valores iniciales.

## Impact

- **Código:**
  - `buscador_vacantes/config.py`: campo `paginas_nucleo` y validación de la reserva en requests.
  - `buscador_vacantes/rotacion.py`: lote con páginas y avance por palabra clave.
  - `buscador_vacantes/fuentes/base.py`: la petición recibe la página y se corta la paginación.
  - `fuentes/computrabajo.py` y `fuentes/elempleo.py`: parámetro de página.
  - Firma `construir_peticion(keyword, pagina=1)` en todas las fuentes.
- **Configuración:** secciones `palabras_clave` y `fuentes` de `config.yaml`.
- **Pruebas:** `tests/test_config.py`, `tests/test_fechas_rotacion.py`, `tests/test_fuente_base.py` y las pruebas de Computrabajo y elempleo.
- **Documentación:** `README.md`.
- **Producción (PC Fedora):**
  - Se despliega con `git pull`; no cambia el esquema de la base.
  - Cada corrida pasa de 18 a 25 requests, ~1 min más de duración, lejos del límite de 28 min.
  - La posición de rotación guardada sigue siendo válida.
