## Context

Ver proposal.md. Estado medido sobre `main` (`d9d415f`, 2026-10-14). `assets/` tiene 15 archivos (3,6 MB) y `docs/` 22 (1,6 MB). Referencias encontradas:
- Código: `asistente/respuestas.py` (`banco_preguntas.yaml`), `asistente/tecnologias.py` (`tecnologias.yaml`), `asistente/nucleo.py` (`assets/selectores`), `asistente/cv_pdf.py` (`assets/fuentes`), `radar/fuentes/spe.py` (`assets/certs/…pem`), `comun/config.py` (valor por defecto de `banner.imagen`).
- Configuración: `config.yaml:871` (`imagen: assets/encabezado_vacantes.jpg`). `config.local.yaml` del Fedora no define `imagen`.
- Pruebas: `tests/radar/test_publicacion.py` (la ruta de la imagen) y `tests/asistente/test_extension.py` (`assets/selectores`).
- Documentos: `README.md` (`assets/logo.jpg` y el árbol), `deploy/INSTALAR.md`, `CLAUDE.md` y `openspec/config.yaml` (ambos citan `docs/buscador-vacantes-spec.md`), comentarios de `extension/adaptadores/*.js`.
- Sin ninguna referencia: `logo_v1.jpg` y `logo_v2.jpg`; tampoco `welcome_banner.jpg` (solo existe el archivo) y `logo_emblema.png` solo se cita en un change antiguo. `docs/referencia_hermes/` es material histórico del cronjob anterior.

## Goals / Non-Goals

**Goals:**
- Estructura `assets/{marca,radar,asistente}` y `docs/{radar,asistente,referencia,decisiones}`.
- Rutas actualizadas en un solo paso, con búsqueda final de rutas viejas.
- Un ADR que explique la arquitectura de paquetes.

**Non-Goals:**
- Cambiar el contenido de los recursos o de los documentos (salvo las rutas citadas).
- Dividir `conversacion.py` (fase 3) ni perfiles en `control.db` (fase 4).
- Reordenar `extension/` o `deploy/`.

## Decisions

- **Reparto:** `marca/` = `logo.jpg`, `logo_emblema.png`, `welcome_banner.jpg`. `radar/` = `encabezado_vacantes.jpg`, `certs/`. `asistente/` = `banco_preguntas.yaml`, `tecnologias.yaml`, `selectores/`, `fuentes/`. `docs/radar/` = `buscador-vacantes-spec.md` y el diagnóstico de falsos positivos; `docs/asistente/` = `guia-usuario.md`, el PDF y `tienda-edge/`; `docs/referencia/` = `referencia_hermes/`. `welcome_banner.jpg` va a `marca/` porque no tiene referencias y es identidad visual; se confirma con el dueño.
- **Mismo orden que la fase 1:** primero `git mv` solo (commits separados), luego las rutas, luego las pruebas, para conservar el historial con `git log --follow`.
- **Rutas en una sola constante cuando se pueda:** cada módulo ya define su constante (`RUTA_BANCO`, `RUTA`, etc.); solo se cambia su valor, sin crear una capa nueva.
- **`config.yaml`:** se cambia únicamente `banner.imagen`; el valor por defecto de `config.py` se mantiene igual al del YAML. Como producción lee `config.yaml` del repositorio, no hace falta tocar el `config.local.yaml`.
- **CLAUDE.md y `openspec/config.yaml`:** solo se actualiza la ruta citada de la especificación de origen; el dueño lo confirma al aplicar, por ser archivos de instrucciones.
- **Prueba de rutas:** una prueba que recorre las constantes de ruta del código y falla si algún recurso no existe, para que un movimiento futuro no deje rutas rotas sin aviso.
- **Borrado de `logo_v1` y `logo_v2`:** solo con confirmación expresa; si no se confirma, se mueven a `assets/marca/` en lugar de borrarse.
- **ADR:** `docs/decisiones/0001-paquetes-comun-radar-asistente.md` con contexto, decisión (regla `comun ← asistente ← radar`, el radar puede importar del asistente), alternativas descartadas (desacoplamiento total) y consecuencias.

## Risks / Trade-offs

- Una ruta olvidada rompe un recurso solo en ejecución (PDF sin tipografía, encabezado ausente, selectores sin cargar, TLS del SPE): se cubre con la prueba de rutas, la suite y una verificación manual de cada uno.
- `config.yaml` se lee en producción: el `git pull` y el reinicio del asistente deben ir juntos; el radar toma la imagen en su próxima corrida.
- Referencias fuera del repositorio (guías enviadas a usuarios, ficha de la tienda de Edge) pueden citar `docs/…`; se revisan en `docs/asistente/` y se avisa al dueño si alguna cita una ruta del repositorio.
- Los planes de changes abiertos y archivados pueden citar rutas viejas; se actualizan solo los abiertos, no el archivo histórico.
- Binarios movidos (PDF, imágenes) abultan el diff pero no el historial, porque `git mv` los detecta como renombres.
