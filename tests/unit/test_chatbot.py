"""Pruebas unitarias. Las de motor e integración necesitan Neo4j levantado y el grafo cargado."""
import pytest

from app.nlp.nlp import extraer_asignaturas, extraer_filtro, normalize
from scripts.load_graph import parse_requisitos

CAT = [{"codigo": "7987", "nombre": "Cálculo I", "alias": None},
       {"codigo": "7988", "nombre": "Cálculo II", "alias": None},
       {"codigo": "8320", "nombre": "Física II (Electricidad y Magnetismo)", "alias": None},
       {"codigo": "1197", "nombre": "Inteligencia Artificial", "alias": ["ia"]}]


def test_normalize():
    assert normalize("¿Qué necesito para Cálculo 2?") == "que necesito para calculo ii"
    assert normalize("materia 0741") == "materia 0741"  # el código conserva el cero inicial
    assert normalize("estructura de datos ll") == "estructura de datos ii"


def test_parse_requisitos():
    assert parse_requisitos("0709 8322") == ([("0709", "previo"), ("8322", "previo")], None)
    assert parse_requisitos("S 8394 1548") == ([("8394", "S"), ("1548", "previo")], None)
    assert parse_requisitos("CURSAR IV AÑO") == ([], "CURSAR IV AÑO")
    assert parse_requisitos("") == ([], None)


@pytest.mark.parametrize("texto,codigos", [
    ("¿qué necesito para cálculo II?", ["7988"]),          # gana el nombre más largo, no "Cálculo I"
    ("aprobé calculo 1, ¿puedo ver calculo 2?", ["7987", "7988"]),
    ("prerrequisitos de IA", ["1197"]),                   # alias
    ("¿qué necesito para Cálculo IV?", []),               # no existe: no debe confundirse con Cálculo I
    ("requisitos de fisica 2", ["8320"]),                 # nombre sin el paréntesis
    ("materia 7987", ["7987"]),
])
def test_extraer_asignaturas(texto, codigos):
    assert [e["codigo"] for e in extraer_asignaturas(texto, CAT) if e["score"] >= 90] == codigos


def test_extraer_filtro():
    assert extraer_filtro("materias de cuarto año segundo semestre") == {"anio": "IV", "sem": "II"}
    assert extraer_filtro("asignaturas de 3er año") == {"anio": "III"}
    assert extraer_filtro("materias del verano") == {"sem": "Verano"}


def test_motor_memoria_multiturno():
    engine = pytest.importorskip("app.inference.engine")
    mem = {}
    r1 = engine.responder("¿Qué prerrequisitos tiene Base de Datos II?", mem)
    assert r1["tipo"] == "respuesta" and "Base de Datos I" in r1["respuesta"]
    r2 = engine.responder("¿y en qué semestre se ve?", mem)  # no repite la materia
    assert r2["tipo"] == "respuesta" and "III año" in r2["respuesta"]
    engine.responder("ya aprobé Base de Datos I, ¿puedo inscribir Base de Datos II?", mem)
    assert "0856" in mem["aprobadas"]
