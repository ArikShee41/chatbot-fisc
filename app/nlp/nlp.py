"""Módulo NLP: normalización, clasificador de intenciones y extractor de entidades (Hito 2, 4.2)."""
import csv
import re
import unicodedata

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

# Hito 2, sección 8: si P < umbral se pide aclaración. Alpha usó 0.70; calibrado en el conjunto dev
# para el Beta: con 8 clases P rara vez pasa 0.70 y se rechazaban intenciones correctas.
UMBRAL_P = 0.45
FUERTE, DEBIL = 90, 75  # umbrales de similitud para entidades


def normalize(texto):
    """Minúsculas, sin tildes ni signos. Los códigos de 4 dígitos quedan como texto ('0104')."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = " ".join(re.sub(r"[^a-z0-9ñ]+", " ", t).split())
    # Beta: "calculo 2" / "estructura de datos ll" -> numeración romana como en el plan
    t = re.sub(r"(?<=[a-z]) ([1-5])\b", lambda m: " " + ["i", "ii", "iii", "iv", "v"][int(m.group(1)) - 1], t)
    return re.sub(r"\bll\b", "ii", t)


def entrenar_clasificador(catalogo, ruta="data/preguntas/train.csv"):
    filas = list(csv.DictReader(open(ruta, encoding="utf-8")))
    # Beta: n-gramas de caracteres (tolera "inclusiones" vs "inclusion" y faltas de ortografía)
    modelo = make_pipeline(TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True),
                           LogisticRegression(max_iter=2000, C=10))
    modelo.fit([enmascarar(f["pregunta"], catalogo) for f in filas], [f["intencion"] for f in filas])
    return modelo


def enmascarar(texto, catalogo):
    """Beta: reemplaza las asignaturas por 'asignatura' para que sus palabras ("Inteligencia Artificial",
    "Graduación I") no influyan en la intención."""
    q = normalize(texto)
    for e in sorted(extraer_asignaturas(texto, catalogo), key=lambda e: e["inicio"], reverse=True):
        q = q[:e["inicio"]] + "asignatura" + q[e["fin"]:]
    return q


def clasificar(modelo, texto, catalogo):
    """Devuelve (intención, P) con P = probabilidad de la clase más probable."""
    probs = modelo.predict_proba([enmascarar(texto, catalogo)])[0]
    i = probs.argmax()
    return str(modelo.classes_[i]), float(probs[i])


def _en_limites(q, ini, fin):
    """Beta: la coincidencia debe empezar y terminar en límite de palabra ("calculo iv" no es "calculo i")."""
    return (ini == 0 or q[ini - 1] == " ") and (fin == len(q) or q[fin] == " ")


def extraer_asignaturas(texto, catalogo):
    """catalogo: lista de dicts {codigo, nombre, alias}. Devuelve entidades ordenadas por posición en el texto:
    [{codigo, nombre, score, inicio, fin}]. Score >= FUERTE se acepta; entre DEBIL y FUERTE es dudosa."""
    q = normalize(texto)
    candidatos = []
    for a in catalogo:
        sin_parentesis = normalize(re.sub(r"\(.*?\)", "", a["nombre"]))
        exactos = [a["codigo"], sin_parentesis] + [normalize(x) for x in a.get("alias") or []]
        m = next((m for x in exactos for m in [re.search(rf"\b{re.escape(x)}\b", q)] if m), None)
        if m:
            candidatos.append({**a, "score": 100.0, "inicio": m.start(), "fin": m.end()})
        # fuzzy para faltas de ortografía; sin el paréntesis: "Física II (Electricidad...)" -> "fisica ii"
        al = fuzz.partial_ratio_alignment(sin_parentesis, q, score_cutoff=DEBIL)
        if al and _en_limites(q, al.dest_start, al.dest_end):
            candidatos.append({**a, "score": al.score, "inicio": al.dest_start, "fin": al.dest_end})
    # el mejor score gana; en empate, el nombre más largo ("Cálculo II" antes que "Cálculo I")
    candidatos.sort(key=lambda c: (c["score"], len(c["nombre"])), reverse=True)
    elegidos = []
    for c in candidatos:
        if all(c["codigo"] != e["codigo"] and (c["fin"] <= e["inicio"] or c["inicio"] >= e["fin"]) for e in elegidos):
            elegidos.append(c)
    return sorted(elegidos, key=lambda c: c["inicio"])


ANIOS = {"primer": "I", "primero": "I", "segundo": "II", "tercer": "III", "tercero": "III",
         "cuarto": "IV", "quinto": "V"}


def extraer_filtro(texto):
    """'cuarto año segundo semestre' -> {'anio': 'IV', 'sem': 'II'}"""
    q = normalize(texto)
    filtro = {}
    m = re.search(r"\b(primer|primero|segundo|tercer|tercero|cuarto|quinto|([1-5])(?:er|ro|do|to)?)\s+ano\b", q)
    if m:
        filtro["anio"] = ["I", "II", "III", "IV", "V"][int(m.group(2)) - 1] if m.group(2) else ANIOS[m.group(1)]
    m = re.search(r"\b(primer|segundo)\s+semestre\b", q)
    if m:
        filtro["sem"] = "I" if m.group(1) == "primer" else "II"
    if "verano" in q:
        filtro["sem"] = "Verano"
    return filtro
