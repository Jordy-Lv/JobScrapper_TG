# Design

## Context

Las fuentes heredan de `fuentes/base.Fuente` (`construir_peticion(keyword, pagina)` y `parsear`). La corrida (`corrida._consultar`) arma para cada fuente un lote de `Consulta` con la rotación de palabras clave. Desde `priorizar-practicas-aprendiz` existen `soporta_paginas`, `tamano_pagina` y `paginas_nucleo`.

API del SPE, verificada desde el servidor el 2026-10-04:
- **Petición:** `GET https://www.buscadordeempleo.gov.co/backbue/v1/vacantes/resultados?page=N&PLAZA_PRACTICA=1`.
  - Devuelve 50 resultados por página, ordenados por `FECHA_PUBLICACION` descendente (página 1 del 26-sep, página 15 de 2024).
  - Los nombres de filtro son nombres de columna; uno desconocido responde `{"error": "Invalid column name ..."}`.
- **Campos:** `CODIGO_VACANTE`, `TITULO_VACANTE` (con prefijo "PL-"), `DESCRIPCION_VACANTE`, `MUNICIPIO`, `DEPARTAMENTO`, `FECHA_PUBLICACION`, `FECHA_VENCIMIENTO`, `RANGO_SALARIAL`, `TELETRABAJO`, `PLAZA_PRACTICA` y `DETALLES_PRESTADOR[]` (`NOMBRE_PRESTADOR`, `URL_DETALLE_VACANTE`).
- **Origen de las 743 plazas de práctica:** 316 de elempleo y 292 de Magneto (el `CODIGO_VACANTE` coincide con el id del portal) y ~135 de bolsas universitarias. Retraso de ~8 días: lo más reciente publicado es del 26-sep.
- **TLS:** el servidor envía solo el certificado final, emitido por "GeoTrust TLS RSA CA G1" (DigiCert), y `openssl` devuelve "unable to verify the first certificate".

## Goals / Non-Goals

**Goals:**
- Sumar las plazas de práctica del SPE sin duplicar lo que ya llega por elempleo o Magneto.
- Mantener la verificación TLS.

**Non-Goals:**
- Vacantes del SPE que no son de práctica.
- Pedir el detalle de cada plaza (no hace falta un request extra).
- Integrar directamente las bolsas universitarias o Coally.

## Decisions

**1. Fuente de consulta fija, fuera de la rotación.**
- La clase declara `consulta_fija = "plazas de práctica"`. Si la tiene, `corrida._consultar` arma el lote `[Consulta(consulta_fija, "nucleo", p) for p in 1..presupuesto]` y no mueve la rotación.
- `construir_peticion` ignora la palabra clave y pide `page=p&PLAZA_PRACTICA=1`.
- Se reutilizan `soporta_paginas = True` y `tamano_pagina = 50`, así que una página incompleta corta las siguientes.
- Se descartó filtrar por `DESCRIPCION_VACANTE` con las palabras clave: es búsqueda por subcadena ("practicante sistemas" da 0) y dejaría fuera plazas de TI cuya descripción usa otros términos. Los filtros por reglas y la IA ya separan lo que es TI.

**2. Mapeo al portal de origen.**
- En `DETALLES_PRESTADOR` se busca una entrada cuya URL sea de `elempleo.com` o `magneto365.com`; si existe, la vacante usa `fuente = "elempleo" | "magneto"`, `id_fuente = CODIGO_VACANTE` y esa URL.
- Si no, usa `fuente = "spe"`, `id_fuente = CODIGO_VACANTE` y la URL de la primera entrada.
- En los mensajes, la vacante muestra el portal donde se postula.
- Se descartó dejar todo como `spe:<id>`: la deduplicación por huella no las uniría, porque el título lleva "PL-" y la empresa es distinta. Saldrían repetidas.

**3. Campos.**
- `titulo` sin "PL-".
- `empresa` vacía: el prestador (LEADERSEARCH, MAGNETO GLOBAL, la universidad) no es el empleador, y la spec prohíbe inventar. Con empresa vacía, la huella se basa en la clave.
- `ubicacion` = "Municipio, Departamento" con mayúsculas normalizadas, o "Colombia" si es para todo el territorio.
- `modalidad` = "Remoto" si `TELETRABAJO=1`; si no, vacía.
- `salario` = `RANGO_SALARIAL`, salvo "A Convenir".
- `publicada` = `FECHA_PUBLICACION` como fecha de Colombia.
- `descripcion` = los primeros 600 caracteres de `DESCRIPCION_VACANTE`, precedidos de "Publicada por <prestador>.", para que la IA tenga contexto.
- Se descartan las plazas sin URL o con `FECHA_VENCIMIENTO` anterior a hoy.
- También se descartan los enlaces que exigen iniciar sesión. Verificado el 2026-10-04: Coally lleva a `/auth/login`, los portales Symplicity de Uninorte, Uniandes y La Sabana redirigen al login o al inicio, y UAO, Poligran, Unipiloto, Cinoc y ANDI son públicos. La regla: la ruta contiene `login` o `auth/`, o el dominio termina en uno de `opciones.dominios_con_login` (`symplicity.com`, `coallytalent.com`, `oficia.uniandes.edu.co`, `talentumsabana.unisabana.edu.co`). Si una plaza tiene varios enlaces, se elige el primero público. Las antiguas las descarta el filtro de antigüedad existente (15 días).

**4. TLS con el intermedio incluido.**
- `assets/certs/geotrust-tls-rsa-ca-g1.pem` se descarga de `cacerts.digicert.com` y se verifica su huella SHA-256 contra la que publica DigiCert.
- La fuente crea su cliente con un `ssl.SSLContext` que carga `certifi.where()` más ese archivo.
- Se descartó `verify=False`: la regla del proyecto lo prohíbe y expondría a respuestas suplantadas.

**5. Configuración.**
```yaml
spe:
  activa: true
  presupuesto: 2
  reservado_nucleo: 1
  filtra_nivel: true   # PLAZA_PRACTICA=1
```
- Se agrega `spe` a `ubicacion.fuentes_colombianas`.
- 2 páginas son las 100 plazas más recientes (~5–6 días de publicaciones), suficiente para un origen que se actualiza con días de retraso.

## Risks / Trade-offs

- [El SPE cambia la API o los nombres de columna] → `parsear` lanza `CambioHTML` si falta `resultados`, y el sistema de incidentes avisa.
- [DigiCert rota el intermedio o el SPE cambia de CA] → La conexión falla con un error TLS registrado como incidente. Se actualiza el PEM; nunca se desactiva la verificación.
- [~8 días de retraso: las plazas llegan viejas] → Se acepta. Las de elempleo y Magneto suelen llegar antes por la fuente directa y se deduplican por clave.
- [Muchas plazas no son de TI] → Las rechazan las reglas (`areas_no_ti`) o, si quedan dudosas, la IA. La caché de clasificaciones por huella evita reclasificar las mismas plazas en cada corrida.
- [Una vacante con `fuente = "elempleo"` producida por la fuente `spe`] → Los intentos y las métricas siguen atribuidos a `spe`, porque usan el nombre de la fuente que hizo el request. Solo cambian la clave, el enlace y el nombre que ve el usuario.

## Migration Plan

1. Desplegar con `git pull` en el servidor.
2. Sin siembra: el objetivo es recibir también las prácticas abiertas hoy. Antes de la primera corrida real se ejecuta `uv run buscador.py --dry-run --fuente spe` en el servidor para revisar cuántas pasarían los filtros. Se esperan pocas decenas, porque la mayoría no son de TI o ya se enviaron por elempleo o Magneto.
3. Rollback: `activa: false` en `config.yaml`.
