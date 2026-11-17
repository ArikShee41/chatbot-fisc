"""Conector Python-Neo4j (puerto P3 del Hito 2)."""
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD")),
)


def run(cypher, **params):
    """Ejecuta una consulta y devuelve los registros como lista de dicts."""
    records, _, _ = driver.execute_query(cypher, params)
    return [r.data() for r in records]
