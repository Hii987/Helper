import json

from app import llm, replies, websearch

from .test_app import _new, _pdf, client  # noqa: F401  (fixture)

INTERVIEW = {
    "type_reponse": "entretien", "entreprise": "Halden Labs SAS", "poste": "Data Engineer",
    "contact_nom": "Maya Lindqvist", "contact_role": "Recruiter", "contact_email": "maya@halden.example",
    "date_entretien": "2026-12-01", "heure": "14:00", "format": "visio",
    "a_faire": "Confirm the slot", "resume": "Halden Labs invites you to an interview.",
}


def _fake_llm(monkeypatch, analysis: dict, prep: str = "## 1. Situation\nVideo interview."):
    calls = []

    async def fake_chat(messages, temperature=0.5, max_tokens=None, json_mode=False):
        calls.append({"messages": messages, "json_mode": json_mode, "max_tokens": max_tokens})
        return json.dumps(analysis) if json_mode else prep

    async def fake_search(query, max_results=8):
        return [{"title": "Halden Labs, data tools", "url": "https://halden.example/about", "snippet": "200 people"}]

    async def fake_fetch(url, max_chars=6000):
        return {"url": url, "title": "Offer", "text": "Requirements: Python, SQL, Airflow"}

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(websearch, "search", fake_search)
    monkeypatch.setattr(websearch, "fetch_page", fake_fetch)
    return calls


def test_reply_updates_matching_application(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, INTERVIEW)
    other = _new(client, company="Globex").json()
    app = _new(client, status="sent", sections=[{"id": "s1", "kind": "contact", "name": "", "email": "hr@halden.example", "extra": []}]).json()

    data = client.post("/api/replies", json={"message": "Hello, we would like to meet you…"}).json()
    saved = data["application"]
    assert data["created"] is False and data["prepare"] is True
    assert saved["id"] == app["id"]
    assert saved["status"] == "positive" and saved["lastStatusChangeAt"]
    assert saved["nextStep"] == {"date": "2026-12-01", "kind": "interview", "label": "14:00 · visio"}
    contact = next(s for s in saved["sections"] if s["kind"] == "contact")
    assert contact["name"] == "Maya Lindqvist"
    assert contact["email"] == "hr@halden.example"  # ce que la personne avait saisi est gardé
    assert saved["replies"][0]["type"] == "entretien"
    assert "Confirm the slot" in saved["replies"][0]["situation"]
    assert client.get(f"/api/applications/{other['id']}").json().get("replies") is None


def test_reply_creates_application_and_contact(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, INTERVIEW | {"entreprise": "Initech", "poste": "Analyst"})
    data = client.post("/api/replies", json={"message": "Hi"}).json()
    saved = data["application"]
    assert data["created"] is True
    assert (saved["company"], saved["jobTitle"], saved["status"], saved["type"]) == ("Initech", "Analyst", "positive", "regular")
    assert saved["uid"] == "u1"
    assert saved["sections"][0]["kind"] == "contact" and saved["sections"][0]["name"] == "Maya Lindqvist"


def test_refusal_closes_and_clears_next_step(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, {"type_reponse": "refus", "entreprise": "Halden Labs", "poste": "Data Engineer"})
    app = _new(client, status="positive").json()
    client.put(f"/api/applications/{app['id']}", json={"type": "regular", "company": "Halden Labs",
                                                         "jobTitle": "Data Engineer", "status": "positive"})
    client.apps[app["id"]]["nextStep"] = {"date": "2026-12-01", "kind": "interview", "label": ""}
    data = client.post("/api/replies", json={"message": "We are sorry…"}).json()
    assert data["application"]["status"] == "refused"
    assert data["application"]["nextStep"] is None
    assert data["prepare"] is False


def test_deadline_becomes_next_step(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, {"type_reponse": "test", "entreprise": "Halden Labs", "date_limite": "2026-12-03",
                            "date_entretien": "not a date", "a_faire": "Do the coding test"})
    _new(client)
    saved = client.post("/api/replies", json={"message": "Test before Dec 3"}).json()["application"]
    assert saved["nextStep"] == {"date": "2026-12-03", "kind": "deadline", "label": "Do the coding test"}


def test_reply_on_chosen_application_and_errors(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, {"type_reponse": "demande_infos", "a_faire": "Call back"})
    app = _new(client, company="Somewhere").json()
    data = client.post("/api/replies", json={"message": "Call me", "applicationId": app["id"]}).json()
    assert data["application"]["id"] == app["id"] and data["created"] is False
    assert client.post("/api/replies", json={"message": " "}).status_code == 400
    assert client.post("/api/replies", json={"message": "x", "applicationId": "nope"}).status_code == 404


def test_prep_uses_offer_cv_pdf_and_research(client, monkeypatch):  # noqa: F811
    calls = _fake_llm(monkeypatch, INTERVIEW)
    monkeypatch.setattr("app.main._pdf_text", lambda content, max_chars=8000: "CV: Airflow pipelines at Acme")
    cv = client.post("/api/files", params={"name": "cv.pdf"}, content=_pdf()).json()
    app = _new(client, sections=[
        {"id": "s1", "kind": "offerLink", "url": "https://halden.example/jobs/1"},
        {"id": "s2", "kind": "company", "summary": "Builds data tools."},
        {"id": "s3", "kind": "cv", "file": cv},
    ]).json()
    client.put("/api/profile", json={"name": "Alex", "cv": "Profile CV"})

    saved = client.post(f"/api/applications/{app['id']}/prep", json={"lang": "en"}).json()
    assert saved["prep"]["text"].startswith("## 1. Situation") and saved["prep"]["lang"] == "en"
    # L'offre lue via son lien est gardée pour la suite.
    assert next(s for s in saved["sections"] if s["kind"] == "offerLink")["rawText"].startswith("Requirements")
    system, prompt = calls[-1]["messages"][0]["content"], calls[-1]["messages"][-1]["content"]
    assert "Always answer in English" in system
    assert "Airflow pipelines at Acme" in system and "Profile CV" not in system  # le CV envoyé prime
    assert "Python, SQL, Airflow" in prompt and "halden.example/about" in prompt and "Builds data tools." in prompt
    assert calls[-1]["max_tokens"] == replies.PREP_MAX_TOKENS


def test_prep_from_key_points_without_link(client, monkeypatch):  # noqa: F811
    calls = _fake_llm(monkeypatch, INTERVIEW)
    app = _new(client, sections=[{"id": "s1", "kind": "keyPoints", "contract": "CDI", "requirements": ["Spark", "dbt"]}]).json()
    client.post(f"/api/applications/{app['id']}/prep", json={})
    prompt = calls[-1]["messages"][-1]["content"]
    assert "Spark" in prompt and "contract : CDI" in prompt
    assert client.post("/api/applications/nope/prep", json={}).status_code == 404


def test_prep_error_is_reported(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, INTERVIEW)

    async def no_quota(*args, **kwargs):
        raise llm.LLMError("Groq limit reached")

    monkeypatch.setattr(llm, "chat", no_quota)
    app = _new(client).json()
    resp = client.post(f"/api/applications/{app['id']}/prep", json={})
    assert resp.status_code == 502 and "Groq limit" in resp.json()["detail"]
    assert "prep" not in client.get(f"/api/applications/{app['id']}").json()


def test_find_application_rules():
    apps = [
        {"id": "1", "company": "Groupe Decathlon Retail", "jobTitle": "Chargé de communication", "status": "refused"},
        {"id": "2", "company": "Capgemini", "jobTitle": "Développeur Python junior", "status": "sent"},
        {"id": "3", "company": "Capgemini", "jobTitle": "Data engineer", "status": "sent"},
    ]
    assert replies.find_application(apps, "Decathlon", "Assistant marketing digital") is None
    assert replies.find_application(apps, "Decathlon", "Chargée de communication")["id"] == "1"
    assert replies.find_application(apps, "Capgemini", "Développeur Python")["id"] == "2"
    assert replies.find_application(apps, "Capgemini", "Chef de projet") is None
    assert replies.find_application(apps[:2], "Capgemini", "Software engineer")["id"] == "2"
    assert replies.find_application(apps, "", "Data engineer") is None


def test_chat_and_write(client, monkeypatch):  # noqa: F811
    seen = []

    async def fake_complete(messages, temperature=0.5, tools=None, **kwargs):
        seen.append(messages)
        return {"content": "Réponse"}

    async def fake_chat(messages, temperature=0.5, **kwargs):
        seen.append(messages)
        return "Texte"

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(llm, "chat", fake_chat)
    client.put("/api/profile", json={"target": "alternance marketing"})
    data = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Salut"}], "lang": "fr"}).json()
    assert data["text"] == "Réponse"
    assert "alternance marketing" in seen[0][0]["content"] and "français" in seen[0][0]["content"]

    assert client.post("/api/write", json={"kind": "letter", "offer": " "}).status_code == 400
    assert client.post("/api/write", json={"kind": "letter", "offer": "Data engineer", "lang": "en"}).json() == {"text": "Texte"}
    assert "Always answer in English" in seen[-1][0]["content"]
    assert client.post("/api/write", json={"kind": "cv"}).status_code == 400  # pas de CV dans le profil
    client.put("/api/profile", json={"cv": "Mon CV"})
    assert client.post("/api/write", json={"kind": "cv"}).status_code == 200
    assert client.post("/api/write", json={"kind": "email", "goal": "thanks", "received": "Merci"}).status_code == 200
    assert client.post("/api/write", json={"kind": "email", "goal": "unknown"}).status_code == 400


def test_profile_roundtrip_and_cv_import(client, monkeypatch):  # noqa: F811
    assert client.get("/api/profile").json()["name"] == ""
    client.put("/api/profile", json={"name": "Alex", "skills": "SQL"})
    assert client.get("/api/profile").json()["skills"] == "SQL"
    me = client.get("/api/me").json()
    assert me["uid"] == "u1" and me["profileFilled"] is True and me["admin"] is False and me["analytics"] == ""
    assert "text" in client.post("/api/profile/cv-text", content=_pdf()).json()
    assert client.post("/api/profile/cv-text", content=b"not a pdf").status_code == 400
