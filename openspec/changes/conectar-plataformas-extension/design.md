> **Alcance decidido el 2026-10-14:** tras medir el volumen real (elempleo 164 vacantes en 30 días; GetOnBoard 1; SPE 0) y revisar los términos, el dueño decidió conectar **solo elempleo**. GetOnBoard y el SPE quedan en paquete de respaldo y se retoman si su volumen crece. El resto de este documento conserva el análisis original de las tres plataformas.

## Context

Ver `proposal.md` (Por qué) para la motivación. Estado observado en el código:

- **Motor genérico.** `extension/motor.js` interpreta pasos declarativos (`detectar`, `clic`, `formulario`, `enviar`…) que entrega el servidor en `assets/asistente/selectores/<plataforma>.json`. `computrabajo.js` (20 líneas) y `magneto.js` (25) solo agregan lo que no se puede expresar como datos. `servicio.js` carga el adaptador solo si la plataforma está en `ADAPTADORES`; si no, inyecta únicamente `motor.js`.
- **Habilitación por datos.** La extensión muestra y opera solo las plataformas con selectores en `selectores_version` y con permiso del usuario. `manifest.json` ya declara `elempleo`, `getonbrd`, `linkedin` y `buscadordeempleo.gov.co` como `optional_host_permissions`, y `portales.js` ya tiene sus dominios, nombres, enlaces de ingreso e inicio. Habilitar una plataforma no exige nueva versión en la tienda.
- **Reconocimiento del dominio.** `asistente/vacantes.py` (`PLATAFORMAS`) solo mapea `computrabajo.com` y `magneto365.com`; cualquier otro dominio da `plataforma_no_soportada` en `nucleo.camino_automatico`. `textos.py` (`NOMBRES_PLATAFORMA` y los enlaces de inicio) y el comentario de `datos.py` también asumen solo esas dos.
- **Interruptor.** `config.yaml → asistente.plataformas.<x>.automatica` decide si la plataforma postula sola o va a respaldo con `plataforma_no_automatica`. También lo cambia `conversacion.py` en tiempo de ejecución.
- **El SPE no es un portal de postulación como los otros.** `radar/fuentes/spe.py` toma de cada plaza el enlace del prestador (`URL_DETALLE_VACANTE`). Si apunta a elempleo o Magneto, la vacante se atribuye a esa fuente; si no, queda como fuente `spe` con el enlace del prestador. Por eso el dominio final de una plaza del SPE casi nunca es `buscadordeempleo.gov.co`.
- **Verificación pendiente.** La tarea 3.1 de `asistente-postulacion-telegram` (reconocimiento con sesión) sigue abierta incluso para Computrabajo y Magneto; los selectores de Magneto marcan `verificado.postulacion: false`.

## Goals / Non-Goals

**Goals:**
- Habilitar la postulación automática de elempleo y GetOnBoard con el método ya probado (términos → reconocimiento → selectores → fixtures → piloto → habilitar), y la del SPE solo si el dominio de sus vacantes lo justifica.
- Poder activar, pausar o corregir cada plataforma desde el servidor, sin versión nueva de la extensión.
- Dejar el proceso repetible como lista de verificación para futuras plataformas.

**Non-Goals:**
- LinkedIn (sus términos prohíben la postulación automatizada).
- ATS externos y bolsas sin selectores (Symplicity, Coally, etc.).
- Cambios en `motor.js`, en el contrato de la API o en la cola, salvo que el reconocimiento destape un caso que no se pueda expresar con los pasos actuales.
- Rediseñar el popup o el flujo del alta.

## Decisions

### 1. Una plataforma a la vez, con interruptor propio
Cada plataforma sigue las etapas: términos → reconocimiento → selectores y fixtures → adaptador (si hace falta) → piloto del dueño → `automatica: true` → invitados. Mientras no se completa, `automatica: false` envía sus vacantes a respaldo.

*Alternativa descartada:* las tres juntas en un solo paso. Una falla en una frenaría a las demás y el piloto mezclaría causas.

*Orden propuesto:* elempleo primero (publica datos JobPosting, ya se lee su detalle y su flujo se parece al de Computrabajo), después GetOnBoard (portal más pequeño, con aplicación a veces externa) y el SPE al final y condicionado (decisión 4).

### 2. Datos primero, adaptador solo si es imprescindible
Se escribe el JSON de selectores con los pasos declarativos existentes y se prueba con fixtures. Un `extension/adaptadores/<x>.js` y su entrada en `ADAPTADORES` solo se crean ante un comportamiento que los datos no expresan (por ejemplo, una aplicación de una sola página que no recarga, como Magneto).

*Alternativa descartada:* un adaptador por plataforma por simetría. Más código que mantener sin necesidad, y cada corrección exigiría publicar la extensión.

*Resultado en elempleo (2026-10-15):* **no se creó adaptador** ni se tocó `motor.js`. Las dos variantes del portal (postulación normal de un clic y rápida con modal), el aviso de datos, la nota VIP y el video opcional caben en pasos opcionales del JSON. Lo único que los datos del portal no decían, que la nota no se puede enviar vacía, lo declara el JSON en `campos_obligatorios` y lo aplica el servidor al recibir el formulario.

### 3. Revisión de términos antes de escribir selectores
Antes del reconocimiento se leen y registran en `docs/asistente/portales.md` los términos de cada portal sobre automatización, bots y uso asistido. Es la misma razón por la que LinkedIn está fuera. Si prohíben la postulación asistida, la plataforma queda en respaldo y no se invierte más.

*Alternativa descartada:* decidirlo después del piloto; obligaría a descartar trabajo ya hecho.

### 4. El SPE se decide con datos reales
Se mide en la base del servidor cuántas vacantes recientes tienen cada dominio de enlace final (consulta de solo lectura a `vacantes.db`). Según el resultado:
- Si las plazas del SPE enlazan sobre todo a elempleo, Magneto o Computrabajo, **ya quedan cubiertas** por la decisión 5 y no hace falta un adaptador del SPE.
- Si una parte relevante apunta a `buscadordeempleo.gov.co`, se hace el reconocimiento y los selectores de esa ruta.
- Si apuntan a bolsas dispersas, el SPE se queda en respaldo y se documenta.

*Alternativa descartada:* construir el adaptador del SPE de antemano por estar ya en `portales.js`. Podría quedar sin uso, y el SPE exige una cuenta con un registro más pesado que el de los portales privados.

### 5. La plataforma se decide por el dominio del enlace final
`vacantes.PLATAFORMAS` pasa a mapear `elempleo.com`, `getonbrd.com` y, si aplica, `buscadordeempleo.gov.co`, además de los actuales. Se decide por el host del enlace, no por la fuente que halló la vacante: una plaza del SPE con enlace a Magneto se postula como Magneto.

*Alternativa descartada:* un campo de plataforma por fuente; confunde los casos del SPE.

### 6. Textos y datos de plataforma consistentes
Los nombres y enlaces de inicio de `textos.py` se completan para las plataformas nuevas y el comentario de `datos.py` deja de listar solo dos. Una prueba falla si una plataforma con `automatica: true` no tiene nombre, selectores y dominio.

*Alternativa descartada:* dejar que el piloto detecte el desfase; aparecería como un mensaje con el nombre vacío.

### 7. Pasos extra del portal: omitir lo opcional, preguntar lo que pide contenido
Reconocimiento de elempleo (2026-10-15): tras pulsar postular salen un aviso de datos y, según el empleador, un video opcional (V-Prez), una nota de presentación u otras preguntas. El motor MUST leer cada paso y resolverlo así:
- **Opcional y sin contenido del usuario** (video, nota con «Omitir este paso»): se omite.
- **Pide contenido** (nota, preguntas del empleador, encuesta): se reutiliza el mecanismo de preguntas pendientes de la card de Telegram (`preguntas-encuesta-con-botones-y-redaccion-ia`): la IA sugiere o redacta con el perfil y el usuario elige con botones, o decide la IA.
- **Implica su imagen o voz** (grabar video): nunca sin su respuesta expresa.
- **Obligatorio y no reconocido**: `formulario_desconocido` y paquete de respaldo, sin enviar.
El objetivo es que la postulación termine exitosa sin que el usuario tenga que entrar al portal.

*Aplicación en elempleo (2026-10-15):* el video de V-Prez sale después de guardar la postulación y se omite con «Omitir»; «Continuar proceso» nunca se pulsa. La nota de presentación (solo ofertas VIP) se lee como formulario antes del envío y `campos_obligatorios` la vuelve obligatoria para el servidor: la IA la redacta o la pregunta va a la card. Un modal con campos obligatorios desconocidos, o la nota o el modal del CV que siguen en pantalla, terminan en `formulario_desconocido` en lugar de darse por enviados. elempleo no tiene cuestionario propio del empleador en el detalle de la oferta.

*Alternativa descartada:* tratar todo paso desconocido como fallo; dejaría sin postular a las vacantes con una nota o un video opcionales, que son una parte importante.

## Risks / Trade-offs

- **Portal con captcha o verificación frecuente** → la plataforma queda en respaldo; no se evaden captchas (regla del proyecto).
- **Términos de uso restrictivos o ambiguos** → decisión conservadora: respaldo, con el motivo documentado y consultado con el dueño.
- **Cambio de marcado del portal sin aviso** → selectores como datos corregibles en el servidor, reporte con evidencia y `automatica: false` para pausar de inmediato.
- **Aplicación externa en GetOnBoard** (algunas ofertas redirigen a otro sitio) → el flujo debe detectar la salida de los dominios permitidos y terminar como `formulario_desconocido` o respaldo, sin llenar nada fuera de ellos.
- **Perfiles largos en el portal** (por ejemplo elempleo) → `completar_perfil` se implementa solo después de que el piloto mínimo funcione; hasta entonces el estado `incompleto` avisa al usuario.
- **Dependencia del reconocimiento del dueño** (su navegador y sus cuentas) → es el cuello de botella; lo demás se prepara en paralelo.
- **Magneto sin verificar con sesión** → el reconocimiento de las plataformas nuevas se hace en la misma jornada que la tarea 3.1, para aprovechar el mismo navegador y los mismos fixtures.

## Migration Plan

1. Fusionar el mapa de dominios y los textos con las plataformas nuevas en `automatica: false`; sin selectores cargados no cambia el comportamiento.
2. Por plataforma: cargar el JSON (`asistente selectores recargar` o reinicio del servicio), probar con el dueño y luego poner `automatica: true`.
3. **Marcha atrás:** `automatica: false` devuelve las vacantes al paquete de respaldo al instante; retirar el JSON oculta la plataforma del popup. Las postulaciones ya hechas no se tocan.
4. Despliegue en el Fedora con `git pull --ff-only` y reinicio del servicio (los comandos de escritura por `ssh fedora` pueden pedir regla o los ejecuta el dueño).

## Open Questions

- ¿El SPE necesita su propia plataforma? Se resuelve con la medición de la decisión 4 y no cambia las demás.
- ¿Los términos de GetOnBoard y elempleo permiten la postulación asistida? Se confirma en la revisión previa; la respuesta decide si cada plataforma continúa.
