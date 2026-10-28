# Proposal

## Why

El canal prioriza prácticas y aprendizaje, y el Servicio Público de Empleo (buscadordeempleo.gov.co) es la única fuente evaluada que ofrece un filtro nativo de plaza de práctica (`PLAZA_PRACTICA`) mediante una API JSON pública, sin login ni captcha. El 2026-10-04 tenía 743 plazas de práctica abiertas:
- 608 son copias de elempleo y Magneto. Igual sirven: el filtro de práctica rescata las que nuestras palabras clave no encuentran.
- ~135 vienen de bolsas de empleo universitarias (Uninorte, La Sabana, Javeriana, Uniandes, Coally, etc.) a las que el buscador no llega por otra vía.

## What Changes

- Nueva fuente `spe` que consulta solo plazas de práctica (`PLAZA_PRACTICA=1`), ordenadas de la más reciente a la más antigua, y lee las primeras páginas en cada corrida. No usa las palabras clave de la rotación, porque el filtro de práctica ya acota la búsqueda y el filtrado por reglas y la IA deciden si es TI.
- Las copias de elempleo y Magneto se identifican con la clave de su portal de origen (`elempleo:<id>`, `magneto:<id>`) y el enlace original. Así el deduplicador las reconoce si ya llegaron o llegan por la fuente directa.
- Se descartan las plazas sin enlace de detalle y las ya vencidas. El título se limpia del prefijo "PL-".
- El servidor del SPE no envía el certificado intermedio (GeoTrust TLS RSA CA G1, de DigiCert). La fuente verifica TLS agregando ese intermedio, incluido en el repositorio. La verificación nunca se desactiva.
- Configuración: fuente `spe` activa, 2 requests por corrida (100 plazas más recientes), marcada como fuente colombiana y con filtro de nivel nativo.

## Capabilities

### New Capabilities

_Ninguna._

### Modified Capabilities

- `busqueda-fuentes`: el requisito "Fuentes independientes y activables" incluye el Servicio Público de Empleo, y se agrega el requisito "Fuente Servicio Público de Empleo" (solo prácticas, mapeo al origen, descarte de vencidas y verificación TLS con el intermedio incluido).

## Impact

- **Código:**
  - Nuevo `buscador_vacantes/fuentes/spe.py`.
  - Registro en `corrida.FUENTES`, con soporte de fuentes de consulta fija que no usan la rotación.
  - Nombre visible en `formato.NOMBRES_FUENTE`.
- **Assets:** nuevo `assets/certs/geotrust-tls-rsa-ca-g1.pem`, el certificado intermedio público.
- **Configuración:** `config.yaml` (`fuentes.spe` y `ubicacion.fuentes_colombianas`).
- **Pruebas:** `tests/test_spe.py` con un fixture JSON real y pruebas de la corrida para la consulta fija.
- **Documentación:** `README.md` (lista de fuentes).
- **Dependencias:** ninguna nueva; `certifi` ya llega con httpx.
- **Producción:** ~96 requests al día al SPE. Las clasificaciones de la IA quedan en caché por huella, así que releer las mismas plazas no gasta llamadas.
