"""Helper : assistant de recherche d'emploi, de stage et d'alternance."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from . import agent, db, jobs, llm, prompts, websearch  # noqa: E402  (après load_dotenv)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="Helper", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------- Modèles ----------

class Profile(BaseModel):
    name: str = ""
    target: str = ""
    location: str = ""
    skills: str = ""
    cv: str = ""


class ChatRequest(BaseModel):
    messages: list[dict]


class LetterRequest(BaseModel):
    offer: str
    company: str = ""
    extra: str = ""


class CvRequest(BaseModel):
    offer: str = ""


class EmailRequest(BaseModel):
    received: str = ""
    goal: str = "reply"
    tone: str = ""
    extra: str = ""


class Application(BaseModel):
    title: str = ""
    company: str = ""
    contract_type: str = ""
    location: str = ""
    url: str = ""
    status: str = "a_postuler"
    applied_on: str = ""
    next_action_on: str = ""
    contact: str = ""
    notes: str = ""


# ---------- Routes ----------

@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def status():
    return {"llm": llm.is_configured(), "france_travail": jobs.is_configured()}


@app.get("/api/profile")
def get_profile():
    return db.get_profile()


@app.put("/api/profile")
def put_profile(profile: Profile):
    return db.save_profile(profile.model_dump())


async def _ask(messages: list[dict], temperature: float = 0.5) -> dict:
    try:
        return {"text": await llm.chat(messages, temperature)}
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        return await agent.run(db.get_profile(), req.messages)
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/letter")
async def cover_letter(req: LetterRequest):
    if not req.offer.strip():
        raise HTTPException(status_code=400, detail="Colle le texte de l'offre.")
    return await _ask(prompts.cover_letter_messages(db.get_profile(), req.offer, req.company, req.extra))


@app.post("/api/cv-review")
async def cv_review(req: CvRequest):
    profile = db.get_profile()
    if not profile["cv"].strip():
        raise HTTPException(status_code=400, detail="Ajoute d'abord ton CV dans l'onglet Profil.")
    return await _ask(prompts.cv_review_messages(profile, req.offer), 0.4)


@app.post("/api/email")
async def email(req: EmailRequest):
    if req.goal not in prompts.EMAIL_GOALS:
        raise HTTPException(status_code=400, detail="Objectif d'e-mail inconnu.")
    return await _ask(prompts.email_messages(db.get_profile(), req.received, req.goal, req.tone, req.extra))


@app.get("/api/jobs")
async def search_jobs(q: str = "", location: str = "", department: str = "", kind: str = "emploi"):
    if kind not in jobs.KINDS:
        raise HTTPException(status_code=400, detail="Type de contrat inconnu.")
    result = {
        "offers": [], "error": None,
        "web": [], "web_error": None,
        "links": jobs.external_links(q, location, kind),
    }

    async def from_france_travail():
        if jobs.is_configured():
            try:
                result["offers"] = await jobs.search(q, department, kind)
            except Exception as exc:  # l'appli reste utilisable via le web et les liens
                result["error"] = str(exc)

    async def from_web():
        if q.strip():
            try:
                result["web"] = await websearch.search_jobs(q, location, kind)
            except Exception as exc:
                result["web_error"] = str(exc)

    await asyncio.gather(from_france_travail(), from_web())
    return result


@app.get("/api/applications")
def list_applications():
    return db.list_applications()


@app.post("/api/applications", status_code=201)
def create_application(application: Application):
    return db.create_application(application.model_dump())


@app.patch("/api/applications/{app_id}")
def update_application(app_id: int, data: dict):
    try:
        updated = db.update_application(app_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Candidature introuvable.")
    return updated


@app.delete("/api/applications/{app_id}", status_code=204)
def delete_application(app_id: int):
    if not db.delete_application(app_id):
        raise HTTPException(status_code=404, detail="Candidature introuvable.")
