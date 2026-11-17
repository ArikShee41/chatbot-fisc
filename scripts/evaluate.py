"""Evaluación con las métricas del Hito 2, sección 10.

Uso: python -m scripts.evaluate <dev|test> <etiqueta>     (ej.: python -m scripts.evaluate test alpha)
Guarda docs/resultados/<etiqueta>_<split>.json y muestra los errores para el análisis.
"""
import csv
import json
import statistics
import sys
from pathlib import Path

from sklearn.metrics import classification_report

from app.graph.db import run
from app.inference.engine import responder

CQ = {"plan_materias": "CQ1", "semestre_materia": "CQ2", "prerrequisitos": "CQ3", "puedo_inscribir": "CQ4",
      "dependientes": "CQ5", "creditos": "CQ10"}
SEGURAS = {"aclaracion", "sin_informacion", "rechazo"}


def entidades_obtenidas(r):
    """Mismo formato que la columna 'entidades' del CSV: código de la asignatura objetivo + filtros."""
    ents = {r["objetivo"]} if r.get("objetivo") else set()
    return ents | {f"{k}:{v}" for k, v in r["filtro"].items() if r["intencion"] == "plan_materias"}


def evaluar(split):
    filas = list(csv.DictReader(open(f"data/preguntas/{split}.csv", encoding="utf-8")))
    casos = []
    for f in filas:
        r = responder(f["pregunta"])
        esperadas = set(f["entidades"].split())
        ok_int = r["intencion"] == f["intencion"]
        ok_tipo = r["tipo"] == f["tipo"]
        ok_ent = (r["tipo"] != "respuesta") or entidades_obtenidas(r) == esperadas
        aprobadas = set(r["entidades"]) - {r["objetivo"]}  # lo que el extractor ve como materias aprobadas
        r["aprobadas"] = sorted(aprobadas)
        ok_apr = not f["aprobadas"] or aprobadas == set(f["aprobadas"].split())
        ok_ver = not f["veredicto"] or r.get("veredicto") == f["veredicto"]
        casos.append({"pregunta": f["pregunta"], "esperado": f, "obtenido": {
            k: r.get(k) for k in ("intencion", "p", "tipo", "objetivo", "filtro", "aprobadas", "veredicto", "regla")},
            "exito": ok_int and ok_tipo and ok_ent and ok_apr and ok_ver,
            "latencia": r["latencia_ms"]})

    y_true = [c["esperado"]["intencion"] for c in casos]
    y_pred = [c["obtenido"]["intencion"] for c in casos]
    rep = classification_report(y_true, y_pred, output_dict=True, zero_division=0)

    con_ent = [c for c in casos if c["esperado"]["tipo"] == "respuesta" and c["esperado"]["entidades"]]
    ent_ok = sum(entidades_obtenidas(c["obtenido"]) == set(c["esperado"]["entidades"].split()) for c in con_ent)

    por_cq = {}
    for intent, cq in CQ.items():
        cs = [c for c in casos if c["esperado"]["intencion"] == intent and c["esperado"]["tipo"] == "respuesta"]
        por_cq[cq] = round(sum(c["exito"] for c in cs) / len(cs), 3) if cs else None

    # degradación progresiva: en casos que NO deben responderse, ¿el sistema evita una respuesta incorrecta?
    dificiles = [c for c in casos if c["esperado"]["tipo"] in SEGURAS]
    degr = sum(c["obtenido"]["tipo"] in SEGURAS for c in dificiles)
    # respuestas incorrectas emitidas con seguridad (lo que la degradación quiere evitar)
    incorrectas = [c for c in casos if c["obtenido"]["tipo"] == "respuesta" and not c["exito"]]

    lat = {k: [c["latencia"][k] for c in casos] for k in ("nlp", "cypher", "total")}
    p95 = lambda v: sorted(v)[int(0.95 * (len(v) - 1))]

    grafo = {
        "ciclos_REQUIERE": run("MATCH p=(a:Asignatura)-[:REQUIERE*1..]->(a) RETURN count(p) AS n")[0]["n"],
        "codigos_duplicados": run("MATCH (a:Asignatura) WITH a.codigo AS c, count(*) AS n WHERE n > 1 "
                                  "RETURN count(c) AS n")[0]["n"],
        "nombres_duplicados": run("MATCH (a:Asignatura) WITH toLower(a.nombre) AS c, count(*) AS n WHERE n > 1 "
                                  "RETURN count(c) AS n")[0]["n"],
        "REQUIERE_repetidas": run("MATCH (a)-[r:REQUIERE]->(b) WITH a, b, count(r) AS n WHERE n > 1 "
                                  "RETURN count(*) AS n")[0]["n"],
    }

    return {
        "split": split, "n": len(casos),
        "intenciones": {k: {m: round(v, 3) for m, v in d.items()} if isinstance(d, dict) else round(d, 3)
                        for k, d in rep.items()},
        "exactitud_entidades": round(ent_ok / len(con_ent), 3),
        "tasa_exito_e2e": round(sum(c["exito"] for c in casos) / len(casos), 3),
        "exito_por_cq": por_cq,
        "completitud_cq": f"{sum(v is not None and v >= 0.8 for v in por_cq.values())}/{len(por_cq)} CQs con éxito >= 80%",
        "degradacion_progresiva": round(degr / len(dificiles), 3),
        "respuestas_incorrectas": len(incorrectas),
        "latencia_ms": {k: {"media": round(statistics.mean(v), 1), "p95": round(p95(v), 1), "max": round(max(v), 1)}
                        for k, v in lat.items()},
        "grafo": grafo,
        "errores": [c for c in casos if not c["exito"]],
    }


if __name__ == "__main__":
    split, etiqueta = sys.argv[1], sys.argv[2]
    res = evaluar(split)
    Path("docs/resultados").mkdir(parents=True, exist_ok=True)
    Path(f"docs/resultados/{etiqueta}_{split}.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    resumen = {k: v for k, v in res.items() if k not in ("errores", "intenciones")}
    resumen["macro_f1"] = res["intenciones"]["macro avg"]["f1-score"]
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    print(f"\n--- {len(res['errores'])} errores ---")
    for e in res["errores"]:
        o, x = e["obtenido"], e["esperado"]
        print(f"* {e['pregunta']}\n    esperado: {x['intencion']}/{x['tipo']} {x['entidades']} {x['aprobadas']} {x['veredicto']}"
              f"\n    obtenido: {o['intencion']}(P={o['p']})/{o['tipo']} {o['objetivo']} {o['filtro']} "
              f"{o.get('aprobadas')} {o.get('veredicto')}")
