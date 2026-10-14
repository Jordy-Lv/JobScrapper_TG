# Portales del asistente: términos, volumen y reconocimiento

Documento del change `conectar-plataformas-extension`. Registra, por portal, si conviene
conectarlo a la extensión, y más adelante el reconocimiento con sesión real (selectores,
indicadores y fixtures).

## Términos de uso (tarea 1.1, revisada el 2026-10-14)

Lectura hecha sobre las páginas públicas. **No es asesoría legal**: ninguna cláusula aparece
con el texto «postulación automatizada» y la decisión final es del dueño (tarea 1.2).

| Portal | Documento | Qué dicen sobre automatización | Conclusión |
|---|---|---|---|
| elempleo | [Términos y Condiciones](https://www.elempleo.com/co/sitio-empresarial/tcc/terminos-y-condiciones), v1.1.0 del 10-02-2026 | Sin cláusula explícita sobre robots, scrapers ni acceso automatizado. Lo más cercano: prohíbe «usar cualquier elemento, diseño, software o rutina para interferir» con el sitio, y limita el acceso a «uso personal y no comercial». | **Dudosa**: no prohíbe expresamente, pero la postulación asistida corre dentro de la sesión del propio usuario y a su ritmo (sin interferir ni uso comercial). Riesgo bajo si se respeta el ritmo y no se evaden captchas. |
| GetOnBoard | [Terms and Conditions Agreement](https://www.getonbrd.com/about/tos), v1.1 del 2026-09-17 | Es el contrato de las **empresas clientes**. Prohíbe «copying or permitting automatic downloading» de su propiedad intelectual y entrenar modelos con la plataforma; puede limitar el uso excesivo de su API. No habla de postular en nombre de alguien ni de bots de candidato. | **Dudosa, poca información**: el texto vigente para candidatos no apareció. Hay que leer las «Platform Policies» antes de cualquier piloto. |
| Servicio Público de Empleo | — | No se revisó: ver la medición de abajo. | Sin objeto por ahora. |

LinkedIn sigue fuera de alcance por sus términos.

## Volumen real de vacantes (tarea 1.3, `vacantes.db` del Fedora, 2026-10-14)

Consulta de solo lectura sobre la tabla `vistas`, agrupada por fuente y dominio del enlace.

**Últimos 30 días** (desde 2026-09-14):

| Fuente | Dominio del enlace | Vacantes | Enviadas al canal |
|---|---|---|---|
| computrabajo | co.computrabajo.com / www.computrabajo.com.co | 301 / 15 | 295 / 15 |
| **elempleo** | www.elempleo.com | **164** | 148 |
| **getonboard** | www.getonbrd.com | **1** | 1 |
| linkedin | co.linkedin.com / www.linkedin.com | 474 / 37 | 463 / 37 |
| magneto | www.magneto365.com | 92 | 86 |
| **spe** | — | **0** | 0 |

**Toda la historia** (desde 2026-07-28): computrabajo 423, linkedin 667, elempleo 181, magneto 92,
**getonboard 3**, remoteok 6 y **spe 0**. Ninguna vacante tiene enlace a `buscadordeempleo.gov.co`.

### Conclusiones

1. **elempleo vale la pena**: 164 vacantes en 30 días, comparable con Magneto y por encima de él.
2. **GetOnBoard casi no aporta**: 1 vacante en 30 días y 3 en toda la historia. El filtro del radar
   (junior y sin experiencia, remoto en español) deja pasar muy pocas.
3. **El SPE no aporta nada hoy**: no hay una sola vacante con esa fuente ni con ese dominio. Las plazas
   con enlace a elempleo o Magneto ya se atribuyen a esos portales.

Según la decisión 4 del `design.md`, el SPE queda en **respaldo** (no se hace su reconocimiento) y el
grupo 6 se omite. Para GetOnBoard se propone lo mismo, y retomarlo solo si el volumen crece.

## Decisión del dueño (tarea 1.2)

**2026-10-14: solo elempleo.** GetOnBoard y el SPE quedan en paquete de respaldo; se retoman únicamente
si su volumen de vacantes crece. Se omiten los grupos 5 y 6 del change.

## Reconocimiento con sesión

### elempleo

Pendiente (tareas 2.1 y 2.5).
