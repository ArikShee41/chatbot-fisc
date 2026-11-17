"""Motor de inferencia + subsistema explicativo (Hito 2, secciones 4.2, 4.3 y 6).

Flujo: NLP (intención + entidades) -> plantilla Cypher -> Neo4j -> reglas -> respuesta con trazas WHY/HOW.
"""
import re
import time

from app.graph.db import run
from app.nlp import nlp

PLANTILLAS = {
    "plan_materias": """MATCH (:PlanDeEstudio {codigo: 'LISC-2025'})<-[:PERTENECE_A]-(a:Asignatura)
        WHERE ($anio IS NULL OR a.anio = $anio) AND ($sem IS NULL OR a.semestre = $sem)
        RETURN a.codigo AS codigo, a.nombre AS nombre, a.anio AS anio, a.semestre AS semestre
        ORDER BY a.anio, a.semestre, a.nombre""",
    "semestre_materia": """MATCH (a:Asignatura {codigo: $codigo})
        RETURN a.nombre AS nombre, a.anio AS anio, a.semestre AS semestre""",
    "prerrequisitos": """MATCH (a:Asignatura {codigo: $codigo})
        RETURN a.nombre AS nombre,
               [(a)-[r:REQUIERE]->(b) | {codigo: b.codigo, nombre: b.nombre, tipo: r.tipo}] AS requiere,
               [(a)-[:TIENE_REQUISITO]->(q) | q.descripcion] AS avance""",
    "dependientes": """MATCH (a:Asignatura {codigo: $codigo})
        RETURN a.nombre AS nombre,
               [(d)-[r:REQUIERE]->(a) | {codigo: d.codigo, nombre: d.nombre, tipo: r.tipo}] AS dependientes""",
    "creditos_asignatura": """MATCH (a:Asignatura {codigo: $codigo}) RETURN a.nombre AS nombre, a.creditos AS creditos""",
    "creditos_plan": """MATCH (:PlanDeEstudio {codigo: 'LISC-2025'})<-[:PERTENECE_A]-(a:Asignatura)
        RETURN sum(a.creditos) AS total, count(a) AS asignaturas""",
}
PLANTILLAS["puedo_inscribir"] = PLANTILLAS["prerrequisitos"]
NECESITA_ASIGNATURA = {"semestre_materia", "prerrequisitos", "puedo_inscribir", "dependientes"}
FUENTE = "Plan de estudio LISC vigente desde el I semestre 2025 (Secretaría General UTP)"

CATALOGO = run("MATCH (a:Asignatura) RETURN a.codigo AS codigo, a.nombre AS nombre, a.alias AS alias")
MODELO = nlp.entrenar_clasificador(CATALOGO)


def _semestre(r):
    return f"{r['anio']} año" + (f", {'verano' if r['semestre'] == 'Verano' else r['semestre'] + ' semestre'}"
                                 if r["semestre"] else "")


def _lista(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def _condiciones(fila):
    """Reglas R1/R2/R4 + avance + marca S sobre los requisitos de una asignatura."""
    previos = [f"{r['nombre']} ({r['codigo']})" for r in fila["requiere"] if r["tipo"] == "previo"]
    simult = [f"{r['nombre']} ({r['codigo']})" for r in fila["requiere"] if r["tipo"] == "S"]
    partes, reglas = [], []
    if previos:
        partes.append("aprobar " + _lista(previos))
    if simult:
        partes.append(_lista(simult) + " (marcada con 'S' en el plan: normalmente indica que puede cursarse "
                      "simultáneamente; confírmalo en Secretaría Académica)")
        reglas.append("RS")
    if fila["avance"]:
        partes.append(_lista([a.lower() for a in fila["avance"]]))
        reglas.append("RA")
    n = len(fila["requiere"]) + len(fila["avance"])
    reglas.insert(0, "R4" if n == 0 else "R1" if n == 1 else "R2")
    return partes, reglas


def responder(texto, memoria=None):
    """Devuelve dict con: respuesta, tipo (respuesta|aclaracion|sin_informacion|rechazo), intencion, p,
    entidades, regla, why, how y latencia_ms. `memoria` es la memoria de trabajo de la sesión (dict)."""
    memoria = memoria if memoria is not None else {}
    t0 = time.perf_counter()
    intencion, p = nlp.clasificar(MODELO, texto, CATALOGO)
    ents = nlp.extraer_asignaturas(texto, CATALOGO)
    fuertes = [e for e in ents if e["score"] >= nlp.FUERTE]
    filtro = nlp.extraer_filtro(texto)
    objetivo = None  # asignatura sobre la que se pregunta; en puedo_inscribir, la que va tras el verbo
    if fuertes and intencion != "plan_materias":
        m = re.search(r"\b(inscribir|llevar|ver|meter|tomar|cursar|matricular|habilitado)\b", nlp.normalize(texto))
        despues = [e for e in fuertes if intencion == "puedo_inscribir" and m and e["inicio"] > m.start()]
        objetivo = (despues or fuertes)[0]
    elif intencion in NECESITA_ASIGNATURA and memoria.get("ultima"):
        objetivo = memoria["ultima"]  # Beta, memoria multi-turno: "¿y en qué semestre se ve?"
    t_nlp = time.perf_counter()

    out = {"intencion": intencion, "p": round(p, 3), "entidades": [e["codigo"] for e in fuertes],
           "objetivo": objetivo and objetivo["codigo"], "filtro": filtro, "regla": None, "how": None}
    plantilla, params = None, {}

    def fin(tipo, respuesta, regla=None):
        t_fin = time.perf_counter()
        out.update(tipo=tipo, respuesta=respuesta, regla=regla or out["regla"])
        out["why"] = (f"Intención '{intencion}' con P={p:.2f}; entidades: "
                      f"{[e['nombre'] for e in fuertes] or 'ninguna'}; plantilla: {plantilla or 'ninguna'}"
                      + (f"; regla: {out['regla']}" if out["regla"] else ""))
        out["latencia_ms"] = {"nlp": round((t_nlp - t0) * 1000, 1),
                              "cypher": out.pop("_t_cypher", 0.0),
                              "total": round((t_fin - t0) * 1000, 1)}
        return out

    if p < nlp.UMBRAL_P:
        return fin("aclaracion", "No estoy seguro de haber entendido. ¿Puedes reformular la pregunta? "
                   "Puedo ayudarte con materias del plan, semestres, prerrequisitos, inscripción y créditos.")
    if intencion in ("fuera_alcance", "fuera_dominio"):
        msg = ("Por ahora solo respondo sobre el plan de estudios de la Lic. en Ingeniería de Sistemas y "
               "Computación (materias, semestres, prerrequisitos y créditos).")
        if intencion == "fuera_alcance":
            msg = "Ese trámite (retiro, inclusión, becas, graduación u otros) aún no está cubierto. " + msg
        return fin("rechazo", msg)

    if intencion in NECESITA_ASIGNATURA or intencion == "creditos":
        if objetivo is None and intencion in NECESITA_ASIGNATURA:
            dudosas = [e for e in ents if e["score"] < nlp.FUERTE]
            if dudosas:
                return fin("aclaracion", f"¿Te refieres a {dudosas[0]['nombre']} ({dudosas[0]['codigo']})?",
                           "R5")
            return fin("aclaracion", "¿Sobre qué asignatura preguntas? Puedes escribir su nombre o su código.",
                       "R5")

    if intencion == "creditos":
        plantilla = "creditos_asignatura" if objetivo else "creditos_plan"
    else:
        plantilla = intencion
    if objetivo:
        params["codigo"] = objetivo["codigo"]
        memoria["ultima"] = objetivo
    if intencion == "plan_materias":
        params = {"anio": filtro.get("anio"), "sem": filtro.get("sem")}

    tc = time.perf_counter()
    filas = run(PLANTILLAS[plantilla], **params)
    out["_t_cypher"] = round((time.perf_counter() - tc) * 1000, 1)
    out["how"] = {"cypher": " ".join(PLANTILLAS[plantilla].split()), "parametros": params, "registros": filas}
    if not filas:
        return fin("sin_informacion", "No encontré información sobre eso en el plan de estudios.", "R5")
    f = filas[0]

    if intencion == "plan_materias":
        titulo = " ".join(x for x in [f"{filtro['anio']} año" if "anio" in filtro else "",
                                       f"semestre {filtro['sem']}" if "sem" in filtro else ""] if x)
        cuerpo = "\n".join(f"- {r['codigo']} {r['nombre']} ({_semestre(r)})" for r in filas)
        return fin("respuesta", f"Materias del plan{' (' + titulo + ')' if titulo else ''}: {len(filas)}\n{cuerpo}"
                   f"\nFuente: {FUENTE}.", "CQ1")
    if intencion == "semestre_materia":
        return fin("respuesta", f"{f['nombre']} se ve en {_semestre(f)} del plan. Fuente: {FUENTE}.", "CQ2")
    if plantilla == "creditos_plan":
        return fin("respuesta", f"El plan tiene {f['total']} créditos en {f['asignaturas']} asignaturas. "
                   f"Fuente: {FUENTE}.", "CQ10")
    if plantilla == "creditos_asignatura":
        return fin("respuesta", f"{f['nombre']} tiene {f['creditos']} créditos. Fuente: {FUENTE}.", "CQ10")
    if intencion == "dependientes":
        deps = [f"{d['nombre']} ({d['codigo']})" for d in f["dependientes"]]
        if not deps:
            return fin("respuesta", f"Según el plan, {f['nombre']} no es prerrequisito de ninguna asignatura. "
                       f"Fuente: {FUENTE}.", "CQ5")
        return fin("respuesta", f"{f['nombre']} es prerrequisito de: {_lista(deps)}. Fuente: {FUENTE}.", "CQ5")

    partes, reglas = _condiciones(f)
    if intencion == "prerrequisitos":
        if not partes:
            return fin("respuesta", f"El plan oficial no establece prerrequisitos para {f['nombre']}. "
                       f"Fuente: {FUENTE}.", "+".join(reglas))
        extra = " Deben cumplirse todos." if reglas[0] == "R2" else ""
        return fin("respuesta", f"Para cursar {f['nombre']} se requiere: {'; '.join(partes)}.{extra} "
                   f"Fuente: {FUENTE}.", "+".join(reglas))

    # puedo_inscribir (R6): SI A REQUIERE B Y B no está aprobada ENTONCES no puede inscribir A
    aprobadas = {e["codigo"] for e in fuertes if e is not objetivo} | set(memoria.get("aprobadas", []))
    memoria["aprobadas"] = out["aprobadas"] = sorted(aprobadas)
    faltan = [r for r in f["requiere"] if r["tipo"] == "previo" and r["codigo"] not in aprobadas]
    faltan_s = [r for r in f["requiere"] if r["tipo"] == "S" and r["codigo"] not in aprobadas]
    reglas.append("R6")
    base = f"Según lo que indicas y el plan oficial, "
    if faltan:
        out["veredicto"] = "no"
        txt = (base + f"no puedes inscribir {f['nombre']}: te falta aprobar "
               + _lista([f"{r['nombre']} ({r['codigo']})" for r in faltan]) + ".")
    elif faltan_s or f["avance"]:
        out["veredicto"] = "depende"
        conds = [f"{r['nombre']} ({r['codigo']}), marcada 'S' (posible correquisito)" for r in faltan_s]
        conds += [a.lower() for a in f["avance"]]
        txt = base + f"para inscribir {f['nombre']} depende de: {_lista(conds)}. Confírmalo en Secretaría Académica."
    else:
        out["veredicto"] = "si"
        txt = base + f"cumples los prerrequisitos de {f['nombre']}."
    return fin("respuesta", txt + f" Fuente: {FUENTE}.", "+".join(reglas))
