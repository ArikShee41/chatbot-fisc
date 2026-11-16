# chatbot-fisc

Chatbot académico para la FISC (UTP) basado en grafo de conocimiento (Neo4j) y NLP.
Hito 3 de Ingeniería de Sistemas Inteligentes.

## Puesta en marcha

1. Copiar `.env.example` a `.env` y poner tu contraseña de Neo4j.
2. Crear el entorno virtual e instalar dependencias:

       python -m venv .venv
       source .venv/Scripts/activate
       pip install -r requirements.txt

3. Levantar Neo4j: `docker compose up -d`
4. Verificar: `python scripts/check_neo4j.py`

## Datos

Los CSV en `data/csv/` son la fuente de verdad. El PDF original del plan de
estudios no se sube al repositorio (`data/raw/` está ignorada).
