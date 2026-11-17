# Hito 3 — Construcción y evaluación del sistema

Chatbot académico FISC · Cubilla, González, Shee · II Semestre 2026

## Introducción

En este hito el diseño del Hito 2 se convirtió en un prototipo funcional. El sistema responde preguntas en
lenguaje natural sobre el plan de estudio de la Licenciatura en Ingeniería de Sistemas y Computación. Para
hacerlo combina un clasificador de intenciones, un extractor de entidades, plantillas Cypher sobre un grafo
de conocimiento en Neo4j, un motor de reglas y un módulo explicativo.

Se construyeron dos versiones, Alpha y Beta, y ambas se evaluaron con las métricas definidas en la sección 10
del Hito 2.

**Alcance del prototipo.** El prototipo cubre las preguntas de competencia CQ1 a CQ5 (plan, semestre,
prerrequisitos, inscripción y dependientes) y la CQ10 (créditos). Las CQ6 a CQ9 (retiro, inclusión, becas y
graduación) quedan fuera de esta etapa. Cuando el estudiante pregunta por ellas, el chatbot responde que
todavía no las cubre, en lugar de inventar una respuesta, como indica la degradación progresiva del Hito 2.

## 5.1 Construcción

### Fuente de conocimiento

La base de conocimiento se construyó a partir del *Plan de Estudio de la Licenciatura en Ingeniería de
Sistemas y Computación* (Secretaría General UTP, formulario FUTP-SG-JRHA-04-1), vigente desde el I semestre
de 2025 y publicado en fisc.utp.ac.pa. El plan se transcribió a `data/csv/asignaturas.csv` y la
transcripción se verificó contra el documento:

- 59 asignaturas, la misma cantidad del plan.
- 221 créditos, el mismo total que indica el plan.
- Cada nodo y cada relación guardan la propiedad `fuente` con el documento de origen (Hito 2, sección 7.2).

### Grafo en Neo4j

| Elemento | Cantidad |
|---|---|
| `Carrera` -[:TIENE_PLAN]-> `PlanDeEstudio` | 1 → 1 |
| `Asignatura` -[:PERTENECE_A]-> `PlanDeEstudio` | 59 |
| `Asignatura` -[:REQUIERE {tipo}]-> `Asignatura` | 40 |
| `Asignatura` -[:TIENE_REQUISITO]-> `Requisito` (avance: "CURSAR IV AÑO", etc.) | 7 relaciones |

El plan marca algunos requisitos con una **S**, por ejemplo Inteligencia Artificial: "S 8394". Esos
requisitos se guardaron como `REQUIERE {tipo: 'S'}`. Como el plan no define la marca, el chatbot la informa
como "posible correquisito, confirmar en Secretaría Académica" y no la trata como un requisito previo
obligatorio. Lo mismo ocurre cuando una celda tiene varios códigos: se interpretan como "todos obligatorios"
(regla R2), interpretación que falta confirmar con el reglamento.

### Componentes implementados

| Componente del Hito 2 | Implementación |
|---|---|
| Módulo de carga (P4) | `scripts/load_graph.py`: CSV → Neo4j; reconstruye el grafo, así actualizar el plan es solo editar el CSV |
| Conector Python-Neo4j (P3) | `app/graph/db.py` |
| Clasificador de intenciones | TF-IDF + regresión logística (scikit-learn), 8 intenciones, con la probabilidad P de la clase elegida |
| Extractor de entidades | Búsqueda exacta (código, nombre, alias) y difusa con `rapidfuzz` contra el catálogo del grafo; umbrales 90 (aceptar) y 75 (preguntar "¿te refieres a…?") |
| Generador de Cypher por plantillas | Una plantilla parametrizada por intención; el usuario nunca escribe Cypher |
| Motor de reglas | R1 (un requisito), R2 (varios, todos obligatorios), R4 (el plan no indica requisitos), R5 (sin información: aclarar o informar), RA (requisito de avance de año), RS (marca S), R6 (inscripción: SI A REQUIERE B Y B no está aprobada ENTONCES no puede inscribir A) |
| Memoria de trabajo | Por sesión: última asignatura mencionada y materias que el estudiante declara aprobadas (no se guardan ni se verifican) |
| Módulo explicativo | Cada respuesta incluye WHY (intención, P, entidades, plantilla y regla) y HOW (Cypher, parámetros y registros devueltos) |
| Gestor de diálogo e interfaz | FastAPI (`POST /chat`) y una página de chat que muestra la respuesta y su explicación |

**Ejemplo de interacción** (motor de inferencia ↔ base de conocimiento):

> **Estudiante:** ya aprobé Inteligencia Artificial, ¿puedo inscribir Aprendizaje Automático?
> **Chatbot:** Según lo que indicas y el plan oficial, no puedes inscribir Aprendizaje Automático: te falta
> aprobar Análisis de Datos y Toma de Decisiones para Computación (1195). *(regla R2+R6)*
> **WHY:** intención `puedo_inscribir`, P = 0.93, entidades: Aprendizaje Automático (objetivo), Inteligencia
> Artificial (aprobada).
> **HOW:** `MATCH (a:Asignatura {codigo: $codigo}) RETURN … [(a)-[r:REQUIERE]->(b) | …]` con
> `codigo = '1496'`; el grafo devuelve 1195 y 1197.

## 5.2 Prototipo Alpha

El Alpha implementó el flujo completo con las decisiones iniciales del Hito 2:

- Clasificador con n-gramas de palabras.
- Umbral de P en 0.70.
- Extractor difuso solo sobre el nombre completo de la asignatura.

Se probó con un conjunto de desarrollo de 36 preguntas etiquetadas. Al revisar los errores uno por uno se
encontraron estos problemas:

| # | Problema | Tipo | Ejemplo |
|---|---|---|---|
| 1 | Umbral de 0.70 demasiado alto: con 8 intenciones y pocos ejemplos, P casi nunca supera 0.70 y se piden aclaraciones aunque la intención sea correcta | Razonamiento | "¿Qué requisitos tiene Gerencia de Proyectos Informáticos?" → intención correcta con P = 0.41, pero el sistema pidió aclarar |
| 2 | Números arábigos y errores de escritura en lugar de romanos | Integración NLP–grafo | "base de datos 2" se reconocía como Base de Datos I; "estructura de datos ll" como Estructura de Datos I |
| 3 | Nombres cortos y siglas no reconocidos | Datos | "Redes", "IA", "Análisis de Datos" |
| 4 | Coincidencias dentro de una palabra | Razonamiento | "Cálculo IV" (no existe) se confundía con Cálculo I |
| 5 | Los nombres de las materias influían en la intención | Arquitectura | "¿qué se habilita cuando paso Inteligencia Artificial?" se clasificaba como `semestre_materia` |
| 6 | Confusión entre intenciones cercanas | Datos de entrenamiento | becas o inclusiones clasificadas como preguntas del plan; "¿Cuánto es 2 más 2?" como `fuera_alcance` |
| 7 | Una mención del nombre exacto se perdía si había otra parecida | Integración | en "aprobé cálculo 1, ¿puedo ver cálculo 2?" solo se detectaba Cálculo II |
| 8 | Sin memoria entre turnos | Arquitectura | "¿y en qué semestre se ve?" no sabía de qué materia se hablaba |

## 5.3 Prototipo Beta

Correcciones aplicadas, con el número del problema que resuelve cada una:

| # | Corrección |
|---|---|
| 1 | Umbral recalibrado en el conjunto de desarrollo: 0.45 aceptaba 32 de 36 preguntas con 1 error, frente a 20 de 36 con 0.70 |
| 2 | La normalización convierte "1–5" y "ll" en numeración romana cuando siguen a una palabra |
| 3 | Archivo `alias.csv` cargado al grafo como propiedad `alias`; es conocimiento, no código, así que se actualiza sin tocar el motor |
| 4 | La coincidencia difusa debe empezar y terminar en un límite de palabra |
| 5 | Antes de clasificar, las asignaturas detectadas se reemplazan por la palabra "asignatura" (enmascarado); el clasificador pasa a n-gramas de caracteres, que toleran plurales y faltas de ortografía |
| 6 | Se agregaron 12 ejemplos de entrenamiento sobre los tipos de error encontrados en desarrollo |
| 7 | Búsqueda exacta del nombre (y del nombre sin el paréntesis, como en "Física II") antes de la difusa |
| 8 | Memoria multi-turno: si falta la asignatura, se usa la última mencionada en la sesión; las materias aprobadas se acumulan |

Además, la regla R5 distingue dos casos:

- Una materia que no existe ("Física Cuántica") recibe "no la encontré en el plan".
- Una pregunta sin materia ("¿Qué prerrequisitos tiene?") recibe una solicitud de aclaración.

Las pruebas automáticas (`pytest`, 10 casos) cubren la normalización, la lectura de requisitos, el extractor
y la memoria multi-turno.

## 5.4 Evaluación

### Diseño experimental

| Conjunto | Preguntas | Uso |
|---|---|---|
| `train` | 99 | Entrenar el clasificador (87 en el Alpha, más 12 en el Beta) |
| `dev` | 36 | Analizar los errores del Alpha y calibrar el umbral; no se usa para reportar resultados |
| `test` | 61 | Resultados finales del Alpha y del Beta; no se usó para entrenar ni calibrar |

Cada pregunta del conjunto de prueba tiene etiquetada:

- la intención;
- el tipo de salida esperado (respuesta, aclaración, sin información o rechazo);
- la asignatura objetivo y las materias aprobadas;
- el veredicto esperado en las preguntas de inscripción (sí, no o depende).

Una pregunta cuenta como **éxito de extremo a extremo** solo si todo coincide.

### Justificación de las métricas

Las métricas son las que el Hito 2 (sección 10) retomó de la revisión sistemática del Hito 1:

- **Precision, recall y F1 por intención.** Se usan en la evaluación comparativa de KBot (Ait-Mlouk & Jiang,
  2020) y, junto con la tasa de éxito y el tiempo de consulta, en el caso gemelo de Ayman et al. (2025).
- **Exactitud de entidades.** Corresponde a la "precisión de entidades" de Tommy et al. (2020).
- **Métricas semánticas** (ciclos y duplicados en el grafo). Verifican la calidad estructural del grafo
  construido a partir de una ontología, en la línea de Chen & Xing (2022).
- **Degradación progresiva.** Responde a la principal limitación que la revisión encontró en los enfoques
  puramente generativos: dar respuestas incorrectas con seguridad (RQ5).

### Resultados (conjunto de prueba, n = 61)

| Métrica (Hito 2, sección 10) | Alpha | Beta |
|---|---|---|
| Precision macro (intenciones) | 0.88 | **0.95** |
| Recall macro (intenciones) | 0.81 | **0.93** |
| **F1 macro (intenciones)** | 0.81 | **0.94** |
| Exactitud de entidades | 0.91 | **0.98** |
| **Tasa de éxito de extremo a extremo** | 0.31 | **0.84** |
| Completitud (CQs con éxito ≥ 80 %) | 1/6 | **5/6** |
| Degradación progresiva (casos que no deben responderse y no se responden) | 1.00 | 1.00 |
| Respuestas incorrectas emitidas | 0 | 1 |
| Latencia total media / p95 (ms) | 1.9 / 4.0 | 2.8 / 3.9 |
| Latencia NLP / Cypher, media (ms) | 0.6 / 1.2 | 1.4 / 1.3 |
| Ciclos en REQUIERE (exactitud semántica) | 0 | 0 |
| Códigos, nombres o relaciones duplicados (concisión) | 0 | 0 |

**Éxito por pregunta de competencia (prueba):**

| CQ | Alpha | Beta |
|---|---|---|
| CQ1 Materias del plan | 0.33 | 0.67 |
| CQ2 Semestre de una materia | 0.67 | 1.00 |
| CQ3 Prerrequisitos | 0.08 | 0.92 |
| CQ4 ¿Puedo inscribir? | 0.60 | 1.00 |
| CQ5 ¿De qué es prerrequisito? | 0.00 | 0.86 |
| CQ10 Créditos | 0.80 | 1.00 |

**F1 por intención (prueba):**

| Intención | Alpha | Beta |
|---|---|---|
| plan_materias | 0.91 | 0.91 |
| semestre_materia | 0.88 | 0.93 |
| prerrequisitos | 0.90 | 0.90 |
| puedo_inscribir | 0.95 | 1.00 |
| dependientes | 0.80 | 0.86 |
| creditos | 1.00 | 1.00 |
| fuera_alcance | 0.73 | 0.91 |
| fuera_dominio | 0.29 | 1.00 |

### Análisis

**Fortalezas.**

- La tasa de éxito subió de 31 % a 84 %. La mayor parte de la mejora viene de dos correcciones: la
  calibración del umbral y la integración entre NLP y grafo (numerales, alias y límites de palabra).
- La separación entre conocimiento y motor funcionó como se diseñó. Los alias y el plan se actualizan en CSV
  sin tocar el código, que es la ventaja de CommonKADS que justificó la arquitectura del Hito 2.
- La latencia queda muy por debajo de la meta de 1000 ms: p95 de 3.9 ms.
- El grafo no tiene ciclos ni duplicados.
- Todas las respuestas citan su fuente y muestran la explicación WHY/HOW.

**Limitaciones.**

- **Una respuesta incorrecta en el Beta.** "¿De qué es requisito Geografía de Panamá?" se clasificó como
  `prerrequisitos` (P = 0.61) y el sistema respondió que la materia no tiene prerrequisitos. La pregunta
  pedía lo contrario: de qué materias es prerrequisito. Las dos intenciones usan casi las mismas palabras.
  Es el error más importante a corregir, porque da información equivocada con seguridad.
- **Aclaraciones de más.** En 6 casos de prueba el sistema pidió aclaración aunque la intención era correcta:
  5 porque P quedó bajo el umbral (entre 0.30 y 0.41) y 1 ("Cálculo IV") porque preguntó "¿te refieres a
  Cálculo I?" en vez de decir que la materia no existe. Esto falla de forma segura, pero baja la tasa de éxito. Saludos como "¿Qué tal?" y
  preguntas generales piden aclarar en lugar de rechazarse, porque `fuera_dominio` tiene pocos ejemplos.
- **Detección de materias inexistentes por mayúsculas.** Si el estudiante escribe todo en minúsculas, el
  sistema pide aclaración en vez de decir "no existe en el plan".
- **Tamaño de los datos.** Los conjuntos son pequeños (61 preguntas de prueba) y los escribió el propio
  equipo. Los resultados indican una tendencia, pero no garantizan cómo se comportará con estudiantes reales.
- **Posible sesgo en dev.** El conjunto de desarrollo se usó para ajustar el Beta, así que su resultado (86 %)
  es optimista. Por eso se reporta el de prueba.
- **Una corrección vista en prueba.** La corrección 7 (nombre sin paréntesis, "Física II") se detectó al
  revisar el conjunto de prueba. Sin ella, la tasa de éxito del Beta era de 80 %.
- **Sin historial institucional.** El sistema no conoce el historial del estudiante: el veredicto de
  inscripción depende de lo que el estudiante declara (Hito 2, sección 9).
- **Interpretaciones pendientes.** Falta confirmar con Secretaría Académica el significado de la marca "S" y
  de las celdas con varios códigos.

### Trabajo futuro

- Más ejemplos de entrenamiento y comparación con clasificadores basados en embeddings.
- Una regla específica para distinguir "requisitos de X" de "X es requisito de".
- Incorporar CQ6 a CQ9 (retiro, inclusión, becas y graduación) a partir del reglamento.
- Validar con estudiantes reales.

## Referencias

- Ait-Mlouk, A., & Jiang, L. (2020). KBot: A knowledge graph based chatbot for natural language
  understanding over linked data. *IEEE Access, 8*, 149220–149230.
- Ayman, G., et al. (2025). Building a smart academic advising chatbot with LLMs and knowledge graphs: A case
  study at Nile University. *IEEE ICMISI 2025*.
- Chen, Y., & Xing, X. (2022). Constructing dynamic knowledge graph based on ontology modeling and Neo4j graph
  database. *IEEE ICAIBD 2022*.
- Tommy, L., Kirana, C., & Riska, L. (2020). The combination of natural language processing and entity
  extraction for academic chatbot. *IEEE CITSM 2020*.
- Universidad Tecnológica de Panamá, Secretaría General (2025). *Plan de estudio: Licenciatura en Ingeniería
  de Sistemas y Computación* (FUTP-SG-JRHA-04-1).
