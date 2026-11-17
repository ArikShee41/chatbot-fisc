"""Backend FastAPI (capa de servicios / gestor de diálogo, Hito 2 sección 3).

Uso: uvicorn app.api.main:app --reload   y abrir http://localhost:8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.inference.engine import responder

app = FastAPI(title="Chatbot FISC")
SESIONES = {}  # memoria de trabajo por sesión; solo vive mientras corre el servidor (Hito 2, 4.1)
UI = Path(__file__).parents[1] / "ui" / "index.html"


class Mensaje(BaseModel):
    sesion: str = Field(max_length=64)
    texto: str = Field(min_length=1, max_length=500)


@app.post("/chat")
def chat(m: Mensaje):
    return responder(m.texto, SESIONES.setdefault(m.sesion, {}))


@app.get("/", response_class=HTMLResponse)
def index():
    return UI.read_text(encoding="utf-8")
