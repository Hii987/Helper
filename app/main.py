"""Helper : centre de suivi des candidatures, avec assistant IA et statistiques d'usage."""

import asyncio
import io
import os
import time
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import pypdfium2 as pdfium
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel

load_dotenv()

from . import agent, analytics, companies, jobs, llm, offer, prompts, replies, store, websearch  # noqa: E402  (après load_dotenv)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_FILE_BYTES = 10_000_000
SECTION_KINDS = {"offerLink", "keyPoints", "company", "cv", "letter", "email", "contact", "custom"}
OFFER_KINDS = {"offerLink", "keyPoints"}
PROFILE_FIELDS = ("name", "target", "location", "skills", "cv")
Lang = Literal["fr", "en"]

app = FastAPI(title="Helper")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class ApplicationIn(BaseModel):
    type: Literal["regular", "spontaneous"]
    company: str
    jobTitle: str = ""
    status: Literal["notsent", "sent", "positive", "refused"]
    sections: list[dict] = []


class OfferRequest(BaseModel):
    url: str = ""
    text: str = ""
    withCompany: bool = False


class ProfileIn(BaseModel):
    name: str = ""
    target: str = ""
    location: str = ""
    skills: str = ""
    cv: str = ""


class ConsentIn(BaseModel):
    analytics: Literal["yes", "no"]


class ReplyRequest(BaseModel):
    message: str
    applicationId: str = ""


class PrepRequest(BaseModel):
    lang: Lang = "fr"


class ChatRequest(BaseModel):
    messages: list[dict]
    lang: Lang = "fr"


class WriteRequest(BaseModel):
    kind: Literal["letter", "cv", "email"]
    offer: str = ""
    company: str = ""
    extra: str = ""
    received: str = ""
    goal: str = "reply"
    tone: str = ""
    lang: Lang = "fr"


class CompanySearchIn(BaseModel):
    what: str
    where: str
    radius: float = 10
    minSize: int = 1
    page: int = 1
    activities: list[str] = []


class CompanyContactIn(BaseModel):
    name: str
    city: str = ""


class SpontaneousIn(BaseModel):
    company: dict
    what: str = ""
    description: str = ""
    lang: Lang = "fr"


class EventsIn(BaseModel):
    events: list[dict]
    session: str = ""


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def current_user(session: str = Cookie("", alias="__session")) -> str:
    """Vérifie le jeton Firebase du cookie __session (seul cookie transmis par Firebase Hosting)."""
    try:
        claims = id_token.verify_firebase_token(session, google_requests.Request(),
                                                audience=os.getenv("FIREBASE_PROJECT_ID"))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Please sign in.") from exc
    return claims["sub"]


def _ai_error(uid: str, event: str, started: float, exc: Exception) -> None:
    analytics.capture(uid, event, {"ok": False, "ms": _ms(started), "error": type(exc).__name__})


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


# ---------- Compte et profil ----------

@app.get("/api/me")
def me(uid: str = Depends(current_user)):
    profile = store.get_profile(uid)
    return {
        "uid": uid, "admin": uid in analytics.admin_uids(), "analytics": profile.get("analytics", ""),
        "profileFilled": bool((profile.get("cv") or "").strip() or (profile.get("skills") or "").strip()),
        "llm": llm.is_configured(),
    }


@app.get("/api/profile")
def get_profile(uid: str = Depends(current_user)):
    profile = store.get_profile(uid)
    return {f: profile.get(f, "") for f in PROFILE_FIELDS}


@app.put("/api/profile")
def put_profile(data: ProfileIn, uid: str = Depends(current_user)):
    saved = store.save_profile(uid, data.model_dump())
    analytics.capture(uid, "profile_saved", {"has_cv": bool(data.cv.strip()), "has_skills": bool(data.skills.strip())})
    return {f: saved.get(f, "") for f in PROFILE_FIELDS}


@app.put("/api/profile/consent")
def put_consent(data: ConsentIn, uid: str = Depends(current_user)):
    store.save_profile(uid, {"analytics": data.analytics})
    analytics.forget_consent(uid)
    analytics.capture(uid, "analytics_accepted")  # n'est enregistré que si la personne a accepté
    return {"analytics": data.analytics}


@app.post("/api/profile/cv-text")
async def cv_text_from_pdf(request: Request, uid: str = Depends(current_user)):
    """Extrait le texte d'un CV en PDF pour remplir le profil (le PDF n'est pas gardé)."""
    content = await request.body()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    text = _pdf_text(content)
    analytics.capture(uid, "cv_imported", {"chars": len(text)})
    return {"text": text}


# ---------- Candidatures ----------

def _validate(data: ApplicationIn) -> None:
    if not data.company.strip():
        raise HTTPException(status_code=400, detail="Company is required.")
    for section in data.sections:
        kind = section.get("kind")
        if kind not in SECTION_KINDS:
            raise HTTPException(status_code=400, detail=f"Unknown section: {kind}")
        if data.type == "spontaneous" and kind in OFFER_KINDS:
            raise HTTPException(status_code=400, detail="A spontaneous application has no job offer.")


def _file_ids(sections: list[dict]) -> set[str]:
    return {s["file"]["id"] for s in sections if (s.get("file") or {}).get("id")}


def _delete_files(file_ids: set[str], uid: str) -> None:
    for file_id in file_ids:
        if (store.get_file_meta(file_id) or {}).get("uid") == uid:
            store.delete_file(file_id)


@app.get("/api/applications")
def list_applications(uid: str = Depends(current_user)):
    return store.list_applications(uid)


@app.get("/api/applications/{app_id}")
def get_application(app_id: str, uid: str = Depends(current_user)):
    application = store.get_application(app_id)
    if application is None or application.get("uid") != uid:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


@app.post("/api/applications", status_code=201)
def create_application(data: ApplicationIn, uid: str = Depends(current_user)):
    _validate(data)
    now = store.now()
    record = {**data.model_dump(), "uid": uid, "createdAt": now, "lastStatusChangeAt": now}
    if data.status != "notsent":
        record["sentAt"] = now
    analytics.capture(uid, "application_created", {"type": data.type, "status": data.status,
                                                   "sections": len(data.sections)})
    return store.create_application(record)


@app.put("/api/applications/{app_id}")
def update_application(app_id: str, data: ApplicationIn, uid: str = Depends(current_user)):
    _validate(data)
    old = get_application(app_id, uid)
    if data.type != old["type"]:
        raise HTTPException(status_code=400, detail="The type of an application cannot change.")
    record = {k: v for k, v in old.items() if k != "id"} | data.model_dump()
    if data.status != old["status"]:
        record["lastStatusChangeAt"] = store.now()
        if data.status != "notsent" and not old.get("sentAt"):
            record["sentAt"] = record["lastStatusChangeAt"]
        analytics.capture(uid, "status_changed", {"from": old["status"], "to": data.status, "source": "form"})
    saved = store.update_application(app_id, record)
    _delete_files(_file_ids(old["sections"]) - _file_ids(data.sections), uid)
    return saved


@app.delete("/api/applications/{app_id}", status_code=204)
def delete_application(app_id: str, uid: str = Depends(current_user)):
    application = get_application(app_id, uid)
    _delete_files(_file_ids(application["sections"]), uid)
    store.delete_application(app_id)
    analytics.capture(uid, "application_deleted", {"status": application["status"]})


# ---------- Réponses de recruteurs et préparation d'entretien ----------

@app.post("/api/replies")
async def recruiter_reply(req: ReplyRequest, uid: str = Depends(current_user)):
    """Message d'un recruteur → candidature retrouvée (ou créée) et mise à jour."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Paste the recruiter's message.")
    started = time.monotonic()
    target = get_application(req.applicationId, uid) if req.applicationId else None
    own = store.list_applications(uid)
    try:
        info = await replies.analyze_reply(req.message, own)
    except llm.LLMError as exc:
        _ai_error(uid, "reply_analyzed", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if target is None:
        target = replies.find_application(own, info.get("entreprise", ""), info.get("poste", ""))
    created = target is None
    record = replies.apply_reply(replies.new_application(info) if created else target, info, req.message)
    record["uid"] = uid
    if created:
        saved = store.create_application(record)
    else:
        saved = store.update_application(target["id"], record)
        if record["status"] != target["status"]:
            analytics.capture(uid, "status_changed", {"from": target["status"], "to": record["status"], "source": "reply"})
    analytics.capture(uid, "reply_analyzed", {"ok": True, "ms": _ms(started), "type": info["type_reponse"],
                                              "created": created, "manual": bool(req.applicationId)})
    return {"application": saved, "analysis": info, "created": created,
            "prepare": info["type_reponse"] in replies.PREPARE_FOR}


def _cv_for(record: dict, uid: str, profile: dict) -> str:
    """CV envoyé pour cette candidature (PDF de la section CV) s'il existe, sinon celui du profil."""
    file_id = (replies.section(record, "cv").get("file") or {}).get("id")
    found = store.get_file(file_id) if file_id else None
    if found and found[0].get("uid") == uid:
        try:
            text = _pdf_text(found[1])
            if text.strip():
                return text
        except HTTPException:
            pass
    return profile.get("cv", "")


@app.post("/api/applications/{app_id}/prep")
async def interview_prep(app_id: str, req: PrepRequest, uid: str = Depends(current_user)):
    record = get_application(app_id, uid)
    started = time.monotonic()
    fetched = await replies.fetch_offer(record)
    if fetched:  # on garde le texte lu pour les prochaines préparations
        link = replies.section(record, "offerLink")
        link["rawText"] = fetched
    profile = store.get_profile(uid)
    profile = {**profile, "cv": _cv_for(record, uid, profile)}
    try:
        text, steps = await replies.prepare(record, profile, req.lang)
    except llm.LLMError as exc:
        _ai_error(uid, "prep_generated", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    record = {k: v for k, v in record.items() if k != "id"}
    record["prep"] = {"text": text, "at": store.now(), "lang": req.lang, "steps": steps}
    analytics.capture(uid, "prep_generated", {"ok": True, "ms": _ms(started), "lang": req.lang,
                                              "has_offer": bool(replies.offer_text(record)),
                                              "research": len([s for s in steps if " : " not in s])})
    return store.update_application(app_id, record)


# ---------- Assistant et rédaction ----------

@app.post("/api/chat")
async def chat(req: ChatRequest, uid: str = Depends(current_user)):
    started = time.monotonic()
    try:
        result = await agent.run(store.get_profile(uid), req.messages, req.lang)
    except llm.LLMError as exc:
        _ai_error(uid, "chat_message", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    analytics.capture(uid, "chat_message", {"ok": True, "ms": _ms(started), "steps": len(result["steps"]),
                                            "offers": len(result["offers"]), "tokens": result["tokens"]})
    return result


@app.post("/api/write")
async def write(req: WriteRequest, uid: str = Depends(current_user)):
    """Lettre de motivation, analyse de CV ou e-mail au recruteur."""
    profile = store.get_profile(uid)
    if req.kind == "letter":
        if not req.offer.strip():
            raise HTTPException(status_code=400, detail="Paste the job offer.")
        messages = prompts.cover_letter_messages(profile, req.offer, req.company, req.extra, req.lang)
    elif req.kind == "cv":
        if not (profile.get("cv") or "").strip():
            raise HTTPException(status_code=400, detail="Add your CV in your profile first.")
        messages = prompts.cv_review_messages(profile, req.offer, req.lang)
    else:
        if req.goal not in prompts.EMAIL_GOALS:
            raise HTTPException(status_code=400, detail="Unknown email goal.")
        messages = prompts.email_messages(profile, req.received, req.goal, req.tone, req.extra, req.lang)
    started = time.monotonic()
    try:
        text = await llm.chat(messages, 0.4 if req.kind == "cv" else 0.5)
    except llm.LLMError as exc:
        _ai_error(uid, "text_written", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    analytics.capture(uid, "text_written", {"ok": True, "ms": _ms(started), "kind": req.kind,
                                            "goal": req.goal if req.kind == "email" else ""})
    return {"text": text}


# ---------- Fichiers PDF ----------

def _open_pdf(content: bytes) -> pdfium.PdfDocument:
    try:
        return pdfium.PdfDocument(content)
    except pdfium.PdfiumError as exc:
        raise HTTPException(status_code=400, detail="This file is not a valid PDF.") from exc


def _read_pdf(content: bytes) -> tuple[int, bytes]:
    """Renvoie le nombre de pages et un aperçu PNG de la première page."""
    pdf = _open_pdf(content)
    page = pdf[0]
    image = page.render(scale=224 / page.get_width()).to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return len(pdf), buffer.getvalue()


def _pdf_text(content: bytes, max_chars: int = 8000) -> str:
    pdf = _open_pdf(content)
    text = "\n".join(page.get_textpage().get_text_range() for page in pdf)
    return text.replace("\r\n", "\n").strip()[:max_chars]


@app.post("/api/files", status_code=201)
async def upload_file(request: Request, name: str, uid: str = Depends(current_user)):
    content = await request.body()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    pages, preview = _read_pdf(content)
    meta = {"name": name, "pages": pages, "addedAt": store.now()}
    file_id = store.save_file({**meta, "uid": uid, "preview": preview}, content)
    analytics.capture(uid, "file_uploaded", {"pages": pages})
    return {**meta, "id": file_id}


@app.get("/api/files/{file_id}")
def download_file(file_id: str, download: bool = False, uid: str = Depends(current_user)):
    found = store.get_file(file_id)
    if found is None or found[0].get("uid") != uid:
        raise HTTPException(status_code=404, detail="File not found.")
    meta, content = found
    disposition = "attachment" if download else "inline"
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(meta['name'])}"})


@app.get("/api/files/{file_id}/preview")
def file_preview(file_id: str, uid: str = Depends(current_user)):
    meta = store.get_file_meta(file_id)
    if meta is None or meta.get("uid") != uid:
        raise HTTPException(status_code=404, detail="File not found.")
    return Response(meta["preview"], media_type="image/png")


# ---------- Offres ----------

@app.post("/api/offer/summary")
async def summarize_offer(req: OfferRequest, uid: str = Depends(current_user)):
    if not req.url.strip() and not req.text.strip():
        raise HTTPException(status_code=400, detail="Give a link or paste the offer text.")
    started = time.monotonic()
    try:
        result = await offer.summarize(req.url, req.text, req.withCompany)
    except websearch.WebSearchError as exc:
        _ai_error(uid, "offer_summarized", started, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except llm.LLMError as exc:
        _ai_error(uid, "offer_summarized", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    analytics.capture(uid, "offer_summarized", {"ok": True, "ms": _ms(started), "from_url": not req.text.strip(),
                                                "with_company": req.withCompany})
    return result


@app.get("/api/jobs")
async def search_jobs(q: str = "", location: str = "", department: str = "", kind: str = "emploi",
                      uid: str = Depends(current_user)):
    if kind not in jobs.KINDS:
        raise HTTPException(status_code=400, detail="Unknown contract type.")
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
    analytics.capture(uid, "job_search", {"kind": kind, "results": len(result["offers"]) + len(result["web"]),
                                          "web_ok": result["web_error"] is None})
    return result


# ---------- Entreprises à démarcher (candidatures spontanées) ----------

@app.post("/api/companies/search")
async def search_companies(req: CompanySearchIn, uid: str = Depends(current_user)):
    if not req.what.strip() or not req.where.strip():
        raise HTTPException(status_code=400, detail="Say what you are looking for and where.")
    started = time.monotonic()
    labels = companies.naf_labels()
    try:
        center = await companies.geocode(req.where)
        if req.activities:  # secteurs déjà choisis (page suivante, secteur retiré par la personne)
            activities = [{"code": c, "label": labels[c]} for c in req.activities if c in labels][:companies.MAX_ACTIVITIES]
        else:
            activities = await companies.choose_activities(req.what)
        if not activities:
            raise companies.CompanySearchError("Choose at least one sector.")
        found = await companies.search(center, activities, req.radius, max(0, req.minSize), max(1, req.page))
    except companies.CompanySearchError as exc:
        analytics.capture(uid, "company_search", {"ok": False, "ms": _ms(started), "error": "search"})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except llm.LLMError as exc:
        _ai_error(uid, "company_search", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    analytics.capture(uid, "company_search", {"ok": True, "ms": _ms(started), "results": len(found["results"]),
                                              "radius": req.radius, "page": req.page})
    return {"center": center, "activities": activities, **found}


@app.post("/api/companies/contact")
async def company_contact(req: CompanyContactIn, uid: str = Depends(current_user)):
    started = time.monotonic()
    try:
        contact = await companies.find_contact(req.name, req.city)
    except companies.CompanySearchError as exc:
        analytics.capture(uid, "company_contact", {"ok": False, "ms": _ms(started), "error": "search"})
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    analytics.capture(uid, "company_contact", {"ok": True, "ms": _ms(started), "website": bool(contact["website"]),
                                               "emails": len(contact["emails"])})
    return contact


@app.post("/api/companies/application")
async def spontaneous_application(req: SpontaneousIn, uid: str = Depends(current_user)):
    started = time.monotonic()
    company = {**req.company, "what": req.what, "description": req.description}
    try:
        email = await companies.write_application(store.get_profile(uid), company, req.lang)
    except llm.LLMError as exc:
        _ai_error(uid, "spontaneous_written", started, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    analytics.capture(uid, "spontaneous_written", {"ok": True, "ms": _ms(started)})
    return email


# ---------- Statistiques d'usage ----------

@app.post("/api/events", status_code=202)
def collect_events(data: EventsIn, uid: str = Depends(current_user)):
    """Événements envoyés par l'interface (pages vues, erreurs) : ignorés sans consentement."""
    return {"stored": analytics.capture_many(uid, data.events, data.session)}


@app.get("/api/stats")
def usage_stats(days: int = 30, uid: str = Depends(current_user)):
    if uid not in analytics.admin_uids():
        raise HTTPException(status_code=403, detail="Statistics are reserved for administrators.")
    return analytics.stats(days)
