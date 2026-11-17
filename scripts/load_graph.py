"""Módulo de carga de datos (puerto P4 del Hito 2): CSV del plan oficial -> Neo4j.

Uso: python -m scripts.load_graph
Borra el grafo y lo vuelve a crear, así una actualización del plan es solo editar el CSV.
"""
import csv

from app.graph.db import run

CSV = "data/csv/asignaturas.csv"
ALIAS = "data/csv/alias.csv"
FUENTE = "Plan de estudio LISC, Secretaría General UTP, vigente desde I semestre 2025 (FUTP-SG-JRHA-04-1)"


def parse_requisitos(texto):
    """'0709 8322' -> ([('0709','previo'), ('8322','previo')], None)
    'S 8394 1548' -> ([('8394','S'), ('1548','previo')], None)  # la S marca solo al código siguiente
    'CURSAR IV AÑO' -> ([], 'CURSAR IV AÑO')"""
    if texto.startswith("CURSAR"):
        return [], texto
    reqs, tipo = [], "previo"
    for tok in texto.split():
        if tok == "S":
            tipo = "S"
        else:
            reqs.append((tok, tipo))
            tipo = "previo"
    return reqs, None


def main():
    filas = list(csv.DictReader(open(CSV, encoding="utf-8")))
    run("MATCH (n) DETACH DELETE n")
    run("""CREATE (:Carrera {codigo: 'LISC', nombre: 'Licenciatura en Ingeniería de Sistemas y Computación'})
                  -[:TIENE_PLAN]->(:PlanDeEstudio {codigo: 'LISC-2025', anio: 2025, fuente: $fuente})""",
        fuente=FUENTE)
    run("""UNWIND $filas AS f
           MATCH (p:PlanDeEstudio {codigo: 'LISC-2025'})
           CREATE (a:Asignatura {codigo: f.codigo, nombre: f.nombre, creditos: toInteger(f.creditos),
                                 anio: f.anio, semestre: f.semestre, fuente: $fuente})-[:PERTENECE_A]->(p)""",
        filas=filas, fuente=FUENTE)
    rels, avance = [], []
    for f in filas:
        reqs, req_avance = parse_requisitos(f["requisitos"])
        rels += [{"a": f["codigo"], "b": b, "tipo": t} for b, t in reqs]
        if req_avance:
            avance.append({"a": f["codigo"], "desc": req_avance})
    run("""UNWIND $rels AS r
           MATCH (a:Asignatura {codigo: r.a}), (b:Asignatura {codigo: r.b})
           CREATE (a)-[:REQUIERE {tipo: r.tipo, fuente: $fuente}]->(b)""", rels=rels, fuente=FUENTE)
    run("""UNWIND $avance AS r
           MATCH (a:Asignatura {codigo: r.a})
           MERGE (q:Requisito {descripcion: r.desc, tipo: 'avance'})
           CREATE (a)-[:TIENE_REQUISITO {fuente: $fuente}]->(q)""", avance=avance, fuente=FUENTE)
    # alias: nombres cortos que usan los estudiantes ("IA", "Redes"); no vienen del plan, los define el equipo
    alias = list(csv.DictReader(open(ALIAS, encoding="utf-8")))
    run("""UNWIND $alias AS x MATCH (a:Asignatura {codigo: x.codigo})
           SET a.alias = coalesce(a.alias, []) + x.alias""", alias=alias)
    n = run("MATCH (a:Asignatura) RETURN count(a) AS n")[0]["n"]
    r = run("MATCH ()-[r:REQUIERE]->() RETURN count(r) AS n")[0]["n"]
    assert n == len(filas) and r == len(rels), f"carga incompleta: {n} asignaturas, {r} REQUIERE"
    print(f"Grafo cargado: {n} asignaturas, {r} relaciones REQUIERE, {len(avance)} requisitos de avance")


if __name__ == "__main__":
    main()
