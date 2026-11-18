import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import jobs, llm, main, store, websearch


@pytest.fixture
def client(monkeypatch):
    """Remplace Firestore par un stockage en mémoire."""
    apps, files = {}, {}

    def create(data):
        app_id = f"a{len(apps) + 1}"
        apps[app_id] = data
        return {**data, "id": app_id}

    def save_file(meta, content):
        file_id = f"f{len(files) + 1}"
        files[file_id] = (meta, content)
        return file_id

    fake = {
        "list_applications": lambda uid: [{**d, "id": k} for k, d in apps.items() if d["uid"] == uid],
        "get_application": lambda k: {**apps[k], "id": k} if k in apps else None,
        "create_application": create,
        "update_application": lambda k, d: apps.__setitem__(k, d) or {**d, "id": k},
        "delete_application": lambda k: apps.pop(k),
        "save_file": save_file,
        "get_file": lambda k: files.get(k),
        "get_file_meta": lambda k: files[k][0] if k in files else None,
        "delete_file": lambda k: files.pop(k),
    }
    for name, fn in fake.items():
        monkeypatch.setattr(store, name, fn)
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_SECRET", raising=False)
    main.app.dependency_overrides[main.current_user] = lambda: "u1"
    with TestClient(main.app) as c:
        c.files = files
        yield c
    main.app.dependency_overrides.clear()


def _pdf() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (200, 280), "white").save(buffer, format="PDF")
    return buffer.getvalue()


def _new(client, **kwargs):
    body = {"type": "regular", "company": "Halden Labs", "jobTitle": "Data Engineer", "status": "notsent"} | kwargs
    return client.post("/api/applications", json=body)


def test_index_served(client):
    assert "Job search center" in client.get("/").text


def test_application_lifecycle(client):
    created = _new(client).json()
    assert created["lastStatusChangeAt"] and "sentAt" not in created
    app_id = created["id"]

    body = {"type": "regular", "company": "Halden Labs", "jobTitle": "Data Engineer", "status": "sent",
            "sections": [{"id": "s1", "kind": "contact", "name": "Maya", "extra": []}]}
    updated = client.put(f"/api/applications/{app_id}", json=body).json()
    assert updated["sentAt"] == updated["lastStatusChangeAt"]
    assert updated["sections"][0]["name"] == "Maya"
    assert client.get("/api/applications").json()[0]["status"] == "sent"

    assert client.delete(f"/api/applications/{app_id}").status_code == 204
    assert client.get(f"/api/applications/{app_id}").status_code == 404


def test_application_validation(client):
    assert _new(client, company=" ").status_code == 400
    assert _new(client, status="a_postuler").status_code == 422
    assert _new(client, sections=[{"kind": "unknown"}]).status_code == 400
    assert _new(client, type="spontaneous", sections=[{"kind": "keyPoints"}]).status_code == 400
    app_id = _new(client).json()["id"]
    body = {"type": "spontaneous", "company": "X", "status": "sent"}
    assert client.put(f"/api/applications/{app_id}", json=body).status_code == 400


def test_pdf_upload_and_cleanup(client):
    ref = client.post("/api/files", params={"name": "CV été.pdf"}, content=_pdf()).json()
    assert ref["pages"] == 1
    assert client.get(f"/api/files/{ref['id']}").content.startswith(b"%PDF")
    assert client.get(f"/api/files/{ref['id']}/preview").headers["content-type"] == "image/png"
    assert "attachment" in client.get(f"/api/files/{ref['id']}", params={"download": 1}).headers["content-disposition"]

    app_id = _new(client, sections=[{"id": "s1", "kind": "cv", "file": ref}]).json()["id"]
    client.delete(f"/api/applications/{app_id}")
    assert client.files == {}


def test_upload_rejects_non_pdf(client):
    assert client.post("/api/files", params={"name": "x.pdf"}, content=b"hello").status_code == 400


def test_offer_summary_from_page(client, monkeypatch):
    async def fake_fetch(url, max_chars=6000):
        return {"url": "https://www.haldenlabs.example/careers/de/", "title": "", "text": "Offer text"}

    async def fake_chat(messages, temperature=0.5, **kwargs):
        assert messages[1]["content"] == "Offer text"
        return json.dumps({"company": "Halden Labs", "salary": None, "responsibilities": ["Build pipelines", " "]})

    monkeypatch.setattr(websearch, "fetch_page", fake_fetch)
    monkeypatch.setattr(llm, "chat", fake_chat)
    data = client.post("/api/offer/summary", json={"url": "https://haldenlabs.example/careers/de"}).json()
    assert data["company"] == "Halden Labs"
    assert data["salary"] == "" and data["requirements"] == []
    assert data["responsibilities"] == ["Build pipelines"]
    assert data["source"] == "haldenlabs.example/careers/de"
    assert data["rawText"] == "Offer text"


def test_offer_summary_errors(client, monkeypatch):
    async def blocked(url, max_chars=6000):
        raise websearch.WebSearchError("Page inaccessible (403).")

    monkeypatch.setattr(websearch, "fetch_page", blocked)
    assert client.post("/api/offer/summary", json={}).status_code == 400
    assert client.post("/api/offer/summary", json={"url": "https://x.example"}).status_code == 422

    monkeypatch.setenv("GROQ_API_KEY", "")
    resp = client.post("/api/offer/summary", json={"text": "Pasted offer"})
    assert resp.status_code == 502 and "GROQ_API_KEY" in resp.json()["detail"]


def test_jobs_without_credentials_returns_links(client, monkeypatch):
    async def fake_search_jobs(q, location="", kind="emploi", max_results=10):
        return [{"title": f"{kind} {q}", "url": "https://www.indeed.fr/x", "snippet": ""}]

    monkeypatch.setattr(websearch, "search_jobs", fake_search_jobs)
    data = client.get("/api/jobs", params={"q": "comptable", "location": "Lyon", "kind": "alternance"}).json()
    assert data["offers"] == []
    names = [l["name"] for l in data["links"]]
    assert "La bonne alternance" in names and "Indeed" in names
    assert data["web"][0]["title"] == "alternance comptable"
    assert client.get("/api/jobs", params={"kind": "cdi"}).status_code == 400


def test_normalize_offer():
    offer = jobs._normalize({
        "id": "123ABC",
        "intitule": "Développeur",
        "lieuTravail": {"libelle": "69 - Lyon"},
        "entreprise": {"nom": "ACME"},
        "typeContratLibelle": "Contrat à durée indéterminée",
        "dateCreation": "2026-10-01T10:00:00.000Z",
        "alternance": True,
    })
    assert offer["company"] == "ACME"
    assert offer["published"] == "2026-10-01"
    assert offer["url"].endswith("/123ABC")


def test_fetch_page_refuses_local_addresses():
    for url in ("http://localhost:8000/", "http://127.0.0.1/", "http://192.168.1.1/", "file:///etc/passwd"):
        with pytest.raises(websearch.WebSearchError):
            asyncio.run(websearch.fetch_page(url))
