import pytest
from fastapi.testclient import TestClient

from app import jobs, llm, main, websearch


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("HELPER_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_SECRET", raising=False)
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    async def fake_chat(messages, temperature=0.5):
        calls.append(messages)
        return "réponse simulée"

    monkeypatch.setattr(llm, "chat", fake_chat)
    return calls


def test_index_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Helper" in resp.text


def test_profile_roundtrip(client):
    assert client.get("/api/profile").json()["name"] == ""
    client.put("/api/profile", json={"name": "Alex", "cv": "Bac+3 informatique"})
    assert client.get("/api/profile").json() == {
        "name": "Alex", "target": "", "location": "", "skills": "", "cv": "Bac+3 informatique",
    }


def test_profile_is_sent_to_llm(client, monkeypatch):
    seen = []

    async def fake_complete(messages, temperature=0.5, tools=None):
        seen.append(messages)
        return {"content": "réponse simulée"}

    monkeypatch.setattr(llm, "complete", fake_complete)
    client.put("/api/profile", json={"name": "Alex", "target": "alternance marketing"})
    resp = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Salut"}]})
    assert resp.json() == {"text": "réponse simulée", "steps": [], "offers": [], "tokens": 0}
    system = seen[0][0]
    assert system["role"] == "system"
    assert "alternance marketing" in system["content"]
    assert seen[0][-1] == {"role": "user", "content": "Salut"}


def test_letter_requires_offer(client, fake_llm):
    assert client.post("/api/letter", json={"offer": "  "}).status_code == 400
    assert client.post("/api/letter", json={"offer": "Développeur web"}).status_code == 200


def test_cv_review_requires_cv(client, fake_llm):
    assert client.post("/api/cv-review", json={}).status_code == 400
    client.put("/api/profile", json={"cv": "Mon CV"})
    assert client.post("/api/cv-review", json={}).status_code == 200


def test_email_goals(client, fake_llm):
    resp = client.post("/api/email", json={"received": "Bonjour, êtes-vous dispo ?", "goal": "accept"})
    assert resp.status_code == 200
    assert "accepter" in fake_llm[0][-1]["content"]
    assert client.post("/api/email", json={"goal": "inconnu"}).status_code == 400


def test_llm_error_without_key(client, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    resp = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Salut"}]})
    assert resp.status_code == 502
    assert "GROQ_API_KEY" in resp.json()["detail"]


def test_applications_crud(client):
    created = client.post("/api/applications", json={"title": "Stage data", "company": "ACME"}).json()
    assert created["status"] == "a_postuler"
    app_id = created["id"]

    updated = client.patch(f"/api/applications/{app_id}", json={"status": "entretien", "notes": "mardi 14h"}).json()
    assert updated["status"] == "entretien" and updated["notes"] == "mardi 14h"
    assert client.patch(f"/api/applications/{app_id}", json={"status": "nimporte"}).status_code == 400

    assert len(client.get("/api/applications").json()) == 1
    assert client.delete(f"/api/applications/{app_id}").status_code == 204
    assert client.delete(f"/api/applications/{app_id}").status_code == 404


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
    assert offer["alternance"] is True
    assert offer["url"].endswith("/123ABC")


def test_llm_error_with_placeholder_key(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "ta_clé_groq")
    resp = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Salut"}]})
    assert resp.status_code == 502
    assert "n'est pas valide" in resp.json()["detail"]
