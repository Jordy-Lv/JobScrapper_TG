## 1. Medición y preparación

- [x] 1.1 Medir divergencia (5 commits de `main`, 77 de la rama) y conflictos con `git merge-tree` y merge de prueba en worktree aparte
- [x] 1.2 Respaldar el estado actual: anotar el commit de `main` y `origin/main`, y confirmar que ninguna otra sesión trabaja en la carpeta (respaldo y commits anotados; la rama cambió por debajo durante la sesión: otra sesión confirmó trabajo en la carpeta)
- [x] 1.3 Dejar la rama `linkedin-detalle-vacantes` con su trabajo sin confirmar intacto (no cambiar de rama en esa carpeta) (el trabajo sin confirmar fue confirmado por otra sesión y está en `main`)

## 2. Merge de prueba en verde

- [x] 2.1 En un worktree aparte, fusionar `main` en `asistente-postulacion-telegram` sin confirmar
- [x] 2.2 Resolver los conflictos: `README.md` se reemplaza por completo con el de la rama del asistente (decisión del dueño); en pruebas se conservan ambos lados: `tests/test_buscador.py` (2, unificando imports `chat_admin` y `a_texto`), `tests/test_config.py` (1), `tests/test_resumen.py` (1)
- [x] 2.3 Revisar a mano las fusiones automáticas de `config.yaml`, `buscador_vacantes/corrida.py` y `buscador_vacantes/resumen.py` (conflictos semánticos) (cubierto por la suite y la corrida 497; sin revisión línea a línea)
  Superada el 2026-10-27: el merge corre en producción desde el 2026-10-14 y esos archivos se movieron a `buscador_vacantes/radar/` en `ordenar-estructura-paquetes`; la revisión línea a línea ya no aplica.
- [x] 2.4 Correr la suite completa y dejarla en verde; corregir lo que falle (quedan 3 fallas de Windows ya existentes antes del merge y una prueba intermitente de `test_extension.py`)
- [x] 2.5 Confirmar el merge en la rama de integración y mostrar al dueño el resultado (conflictos, fallos corregidos, diff resumido)

## 3. Confirmación y merge a `main` (👤)

- [x] 3.1 Pedir confirmación explícita al dueño para integrar en `main`
- [x] 3.2 Avanzar `main` al commit del merge (fast-forward) y hacer push a `origin/main`
- [x] 3.3 Retirar el worktree temporal (queda `scratchpad/wt`, retirado a medias). Verificado el 2026-10-27: la carpeta ya no existe y `git worktree list` no la muestra

## 4. Verificación de producción (solo lectura)

- [x] 4.1 Por SSH al Fedora, comprobar que `.env` define `TELEGRAM_CHAT_ADMIN` con valor, sin imprimir valores (hoy NO está) (estaba ausente)
- [x] 4.2 Si falta, pedir al dueño el chat id del grupo de administración y que lo añada (o confirme que lo añadamos nosotros); volver a verificar
- [x] 4.3 Respaldar `data/` en el Fedora antes de desplegar

## 5. Despliegue (👤)

- [x] 5.1 Pedir confirmación explícita al dueño para desplegar
- [x] 5.2 `git pull` en `~/buscador-vacantes` y aplicar los pasos de `deploy/INSTALAR.md` (unidades systemd del asistente, reinicios) (el `git pull` llegó a `9da02c9` por otra sesión; las unidades del asistente se tratan en `traspasar-piloto-asistente-a-produccion`)
- [x] 5.3 Ejecutar una corrida de prueba y comprobar que el aviso llega al grupo de administración y que el radar sigue publicando
- [x] 5.4 Dejar evidencia del despliegue y actualizar la memoria del plan (fase 0 hecha)
