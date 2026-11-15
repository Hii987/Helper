"""Helper : centre de suivi des candidatures."""

import asyncio
import io
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import pypdfium2 as pdfium
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from . import jobs, llm, offer, store, websearch  # noqa: E402  (après load_dotenv)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_FILE_BYTES = 10_000_000
SECTION_KINDS = {"offerLink", "keyPoints", "cv", "letter", "email", "contact", "custom"}
OFFER_KINDS = {"offerLink", "keyPoints"}

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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


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


@app.get("/api/applications")
def list_applications():
    return store.list_applications()


@app.get("/api/applications/{app_id}")
def get_application(app_id: str):
    application = store.get_application(app_id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found.")
    return application


@app.post("/api/applications", status_code=201)
def create_application(data: ApplicationIn):
    _validate(data)
    now = store.now()
    record = {**data.model_dump(), "createdAt": now, "lastStatusChangeAt": now}
    if data.status != "notsent":
        record["sentAt"] = now
    return store.create_application(record)


@app.put("/api/applications/{app_id}")
def update_application(app_id: str, data: ApplicationIn):
    _validate(data)
    old = get_application(app_id)
    if data.type != old["type"]:
        raise HTTPException(status_code=400, detail="The type of an application cannot change.")
    record = {k: v for k, v in old.items() if k != "id"} | data.model_dump()
    if data.status != old["status"]:
        record["lastStatusChangeAt"] = store.now()
        if data.status != "notsent" and not old.get("sentAt"):
            record["sentAt"] = record["lastStatusChangeAt"]
    saved = store.update_application(app_id, record)
    for file_id in _file_ids(old["sections"]) - _file_ids(data.sections):
        store.delete_file(file_id)
    return saved


@app.delete("/api/applications/{app_id}", status_code=204)
def delete_application(app_id: str):
    application = get_application(app_id)
    for file_id in _file_ids(application["sections"]):
        store.delete_file(file_id)
    store.delete_application(app_id)


# ---------- Fichiers PDF ----------

def _read_pdf(content: bytes) -> tuple[int, bytes]:
    """Renvoie le nombre de pages et un aperçu PNG de la première page."""
    try:
        pdf = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as exc:
        raise HTTPException(status_code=400, detail="This file is not a valid PDF.") from exc
    page = pdf[0]
    image = page.render(scale=224 / page.get_width()).to_pil()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return len(pdf), buffer.getvalue()


@app.post("/api/files", status_code=201)
async def upload_file(request: Request, name: str):
    content = await request.body()
    if len(content) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="The file is larger than 10 MB.")
    pages, preview = _read_pdf(content)
    meta = {"name": name, "pages": pages, "addedAt": store.now()}
    file_id = store.save_file({**meta, "preview": preview}, content)
    return {**meta, "id": file_id}


@app.get("/api/files/{file_id}")
def download_file(file_id: str, download: bool = False):
    found = store.get_file(file_id)
    if found is None:
        raise HTTPException(status_code=404, detail="File not found.")
    meta, content = found
    disposition = "attachment" if download else "inline"
    return Response(content, media_type="application/pdf",
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(meta['name'])}"})


@app.get("/api/files/{file_id}/preview")
def file_preview(file_id: str):
    meta = store.get_file_meta(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return Response(meta["preview"], media_type="image/png")


# ---------- Offres ----------

@app.post("/api/offer/summary")
async def summarize_offer(req: OfferRequest):
    if not req.url.strip() and not req.text.strip():
        raise HTTPException(status_code=400, detail="Give a link or paste the offer text.")
    try:
        return await offer.summarize(req.url, req.text)
    except websearch.WebSearchError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/jobs")
async def search_jobs(q: str = "", location: str = "", department: str = "", kind: str = "emploi"):
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
    return result
