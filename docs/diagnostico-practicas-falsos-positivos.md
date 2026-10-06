# Diagnóstico: falsos positivos en la categoría «prácticas»

Documento de análisis. **No implica cambios de código**: cualquier arreglo debe pasar
por el flujo de OpenSpec del repositorio (`/opsx:propose` → `/opsx:apply` → `/opsx:archive`).

Fecha del análisis: 2026-10-05
Fuente de datos: `data/vacantes.db` (tablas `vistas`, `clasificaciones`, `corridas`)

## 1. Resumen

De las vacantes publicadas en el canal bajo la categoría `practicas`, una parte
significativa **no eran prácticas ni aprendizaje**, sino puestos profesionales de nivel
entry/junior del mercado general.

Medición por día (consulta en la sección 6):

| Día | Marcadas `practicas` | Falsos positivos | % error |
|---|---|---|---|
| 2026-10-04 | 67 | 13 | 19 % |
| 2026-10-05 | 28 | 10 | 36 % |
| 2026-10-06 | 3 | 2 | 67 % |

Nota metodológica: una medición previa de este mismo día reportó 71 % de error porque la
consulta no incluía `%estudiante%` en la lista de términos válidos y comparaba contra un
total incompleto. Los valores de la tabla son los verificados.

El 8 de los 12 falsos positivos identificados el 2026-10-05 provienen de LinkedIn.

## 1.b Casos del 2026-10-06

La única práctica correctamente clasificada del día fue:

- «¡Estamos buscando Aprendices para realizar su etapa práctica!» (Computrabajo). La IA
  emitió el motivo «Práctica profesional en ingeniería de sistemas», correcto.

Los dos falsos positivos fueron:

| Vacante | Fuente | Categoría asignada | Observación |
|---|---|---|---|
| INGENIERO BACKOFFICE - MOTORES | linkedin | practicas | Puesto de ingeniería (área automotriz), no práctica |
| Analista de Innovación y Desarrollo | computrabajo | practicas | Puesto profesional de analista, no práctica |

Ninguno de los dos títulos contiene término de práctica o aprendizaje. La IA los admitió
en `practicas` infiriéndolo del contexto (perfil de estudiante / nivel filtrado por
fuente), no del texto del anuncio.

Motivos emitidos por la IA en la misma corrida, como contraste del sesgo: la misma
llamada rechazó correctamente «Criminalística y ciencias forenses, no es área de TI» y
«Promotor comercial, no es rol de TI». El sesgo es específico de la categoría `practicas`.

## 2. Falsos positivos detectados

| Vacante | Fuente | Hora |
|---|---|---|
| Técnico de soporte - cauca | elempleo | 18:35 |
| Analista de Servicios en la Nube | linkedin | 18:35 |
| Tallerista en Sistematización y Automatización | linkedin | 18:35 |
| Becario/a de Channel Management - Analytics | linkedin | 21:34 |
| Estudiante en Lectiva Tecnico o Tecnologo en Sistemas Informaticas | computrabajo | 22:05 |
| Databricks Engineer Data Engineer (35929) | linkedin | 22:05 |
| AS400 Developer | linkedin | 22:05 |
| ATM Developer Bilingüe – Desarrollo de Software para Cajeros | linkedin | 22:05 |
| Python Developer / Investigación y Desarrollo - Trabajo Remoto | linkedin | 22:05 |
| Ingeniero de integración de datos | linkedin | 22:05 |
| Fullstack Angular & Java | linkedin | 22:05 |
| Ingeniero de Gobierno de Datos/Data Mesh | linkedin | 22:05 |

## 3. Causa raíz

En `config.yaml` la fuente LinkedIn está marcada con:

```yaml
linkedin:
  filtra_nivel: true   # f_E=1,2: solo prácticas y nivel de entrada
```

Ese indicador se propaga al clasificador (`corrida.py`, `_clasificar()` →
`con_filtro = frozenset(n for n, f in ... if f.filtra_nivel)`) y el clasificador lo
interpreta como **evidencia de que la vacante es una práctica**.

Motivos registrados por la IA en `clasificaciones.motivo` que muestran el sesgo:

| Vacante real | Motivo emitido |
|---|---|
| Databricks Engineer Data Engineer | «Práctica de desarrollo de software, **nivel filtrado por fuente**» |
| AS400 Developer | «Práctica de desarrollo AS400, **nivel filtrado por fuente**» |
| Python Developer (BairesDev) | «Práctica de desarrollo Python, **nivel filtrado por fuente**» |
| Fullstack Angular & Java | «Práctica de desarrollo fullstack, **nivel filtrado por fuente**» |
| Ingeniero de Gobierno de Datos | «**Aprendiz** de gobierno de datos, **nivel filtrado por fuente**» |

**El problema de fondo:** en LinkedIn el filtro `f_E=1,2` equivale a *Entry level +
Internship*. «Entry level» **no** significa «práctica»: incluye puestos profesionales
que solo piden poca experiencia. El filtro acota seniority, no naturaleza del contrato.

## 3.b Patrón detectado: el salario como proxy de seniority

En la corrida del 2026-10-06 (≈01:30, fuente elempleo) se publicaron dos vacantes de QA
que, por título y requisitos, corresponden a un nivel superior al de entrada:

| Vacante | Salario publicado | Motivo emitido por la IA |
|---|---|---|
| Profesional qa (SUMMAR) | $3,5 a $4 millones | «QA con 2 años de experiencia y salario de entrada» |
| Qa funcional remoto por 6 meses (confidencial) | $4 a $4,5 millones | «QA funcional, salario de entrada y modalidad remota» |

El segundo motivo es elocuente: la IA **reconoció** que se piden 2 años de experiencia y
aun así clasificó la vacante como aceptable, apoyándose en que el salario le pareció «de
entrada».

Dos observaciones:

1. La política declarada del canal es 0-1 año de experiencia. Una vacante que pide 2 años
   queda fuera de ese rango, con independencia del salario.
2. El salario no es un indicador fiable de seniority: en el mercado colombiano un rango de
   $4 millones para QA corresponde a experiencia media, no a nivel de entrada.

En contraste, en la misma corrida la IA rechazó correctamente «Aprendiz administrativo,
funciones no de TI» y «Analista de inteligencia de mercado y soporte al cliente, no es rol
de TI», lo que confirma que el criterio de área sí funciona y el sesgo está en la
estimación de nivel.

Propuesta: al evaluar el nivel, dar prioridad a la **experiencia exigida explícitamente**
en el anuncio (años, «junior», «sin experiencia», «practicante») por encima del salario
ofrecido.

## 4. Arreglo propuesto (a validar por OpenSpec)

1. **Guardarraíl textual para `practicas`.** La categoría `practicas` debería exigir
   evidencia explícita en el título (o descripción) con términos como:
   `practicante`, `aprendiz`, `aprendizaje`, `pasante`, `pasantía`, `etapa práctica`,
   `etapa productiva`, `contrato de aprendizaje`, `becario`, `estudiante`.
   Sin esa evidencia, la vacante no puede clasificarse como `practicas`.

2. **Reinterpretar `filtra_nivel`.** Que el indicador signifique únicamente
   «la fuente ya acotó el seniority» y **nunca** «es una práctica». Conviene revisar la
   redacción del prompt del clasificador para eliminar la inferencia.

3. **Ruta de escape.** Una vacante sin evidencia de práctica debe ir a su categoría real
   (desarrollo, datos, soporte, …) o, si no encaja, a `otros_ti`; no a `practicas`.

## 5. Hallazgo adicional: corridas sin red mal registradas

Entre 08:32 y 18:00 del 2026-10-05 hubo **20 corridas con todos los contadores en cero**
(corte de internet de ~10 h, ya reportado por el watchdog).

- El sistema se recuperó solo a las 18:32 (sin incidentes abiertos).
- La columna `corridas.sin_red` existe en el esquema pero **no se marcó** en esas filas.
- Efecto: las corridas caídas se cuentan como «vacías», lo que distorsiona las
  estadísticas de rendimiento y la tasa de aceptación.

Propuesta: marcar `sin_red = 1` cuando la causa sea falta de conectividad, para poder
excluirlas de los agregados.

## 6. Consultas de verificación

Falsos positivos del día:

```sql
SELECT v.titulo, v.fuente, v.enviada_en
FROM vistas v
WHERE date(v.enviada_en) = date('now')
  AND v.categoria = 'practicas'
  AND lower(v.titulo) NOT LIKE '%practicante%'
  AND lower(v.titulo) NOT LIKE '%aprendiz%'
  AND lower(v.titulo) NOT LIKE '%pasante%'
  AND lower(v.titulo) NOT LIKE '%práctica%'
  AND lower(v.titulo) NOT LIKE '%practicas%';
```

Corridas sin red no marcadas:

```sql
SELECT id, inicio, crudas, sin_red
FROM corridas
WHERE crudas = 0 AND sin_red = 0;
```

Motivos de rechazo más frecuentes (para calibrar el clasificador):

```sql
SELECT motivo, COUNT(*) veces
FROM clasificaciones
WHERE aceptar = 0
GROUP BY motivo
ORDER BY veces DESC
LIMIT 15;
```
