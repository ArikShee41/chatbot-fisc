import os
import sys

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv()

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.getenv("NEO4J_PASSWORD")

if not password:
    sys.exit("Falta NEO4J_PASSWORD en el archivo .env")

try:
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            session.run("RETURN 1").single()
    print("Conexión a Neo4j OK")
except Exception as e:
    sys.exit(f"Error de conexión a Neo4j: {e}")
