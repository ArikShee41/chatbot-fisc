# chatbot-fisc

Chatbot académico para la FISC (UTP) basado en grafo de conocimiento (Neo4j) y NLP.
Responde sobre el plan de estudio de la Lic. en Ingeniería de Sistemas y Computación (vigente desde 2025):
materias del plan, semestre de una materia, prerrequisitos, si puedes inscribir una materia, de qué materias es
prerrequisito y créditos.

## Para usar

1. Copiar `.env.example` a `.env` y poner tu contraseña de Neo4j.
2. Crear el entorno virtual e instalar dependencias:

       python -m venv .venv
       source .venv/bin/activate        # en Windows: .venv\Scripts\activate
       pip install -r requirements.txt

3. Levantar Neo4j: `docker compose up -d`
4. Verificar: `python scripts/check_neo4j.py`
5. Cargar el grafo: `python -m scripts.load_graph`
6. Abrir el chat: `uvicorn app.api.main:app` y entrar a http://localhost:8000
7. Evaluar: `python -m scripts.evaluate test beta` (resultados en `docs/resultados/`)
8. Pruebas: `pytest`

## Estructura

| Ruta | Qué es (Hito 2) |
|---|---|
| `data/csv/asignaturas.csv` | Plan de estudio oficial (59 asignaturas, 221 créditos) |
| `data/csv/alias.csv` | Nombres cortos que usan los estudiantes ("IA", "Redes") |
| `scripts/load_graph.py` | Módulo de carga de datos (puerto P4) |
| `app/graph/db.py` | Conector Python-Neo4j (puerto P3) |
| `app/nlp/nlp.py` | Clasificador de intenciones (TF-IDF + regresión logística) y extractor de entidades (rapidfuzz) |
| `app/inference/engine.py` | Plantillas Cypher, motor de reglas, memoria de trabajo y módulo explicativo (WHY/HOW) |
| `app/api/main.py`, `app/ui/index.html` | Gestor de diálogo (FastAPI) e interfaz de chat |
| `data/preguntas/` | Preguntas etiquetadas: `train`, `dev` (análisis del Alpha) y `test` (evaluación) |
| `scripts/evaluate.py` | Métricas de la sección 10 del Hito 2 |
| `docs/Hito3_informe.md` | Informe del Hito 3 con resultados Alpha y Beta |
