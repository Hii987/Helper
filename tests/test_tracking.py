import json
import sqlite3

from app import db, llm, tracking, websearch

from .test_app import client  # noqa: F401  (fixture)


def _fake_llm(monkeypatch, analysis: dict):
    calls = []

    async def fake_chat(messages, temperature=0.5, max_tokens=None, json_mode=False):
        calls.append({"messages": messages, "json_mode": json_mode, "max_tokens": max_tokens})
        if json_mode:
            return "Voici le JSON : " + json.dumps(analysis)
        return "## 1. Situation\nEntretien en visio."

    async def fake_search(query, max_results=8):
        return [{"title": "ACME, leader du recyclage", "url": "https://acme.fr/a-propos", "snippet": "ACME emploie 300 personnes"}]

    async def fake_fetch(url, max_chars=6000):
        return {"url": url, "title": "Offre ACME", "text": "Compétences : Python, SQL, anglais courant"}

    monkeypatch.setattr(llm, "chat", fake_chat)
    monkeypatch.setattr(websearch, "search", fake_search)
    monkeypatch.setattr(websearch, "fetch_page", fake_fetch)
    return calls


INTERVIEW = {
    "type_reponse": "entretien", "entreprise": "ACME SAS", "poste": "Data analyst",
    "contact_nom": "Julie Martin", "contact_role": "RH", "contact_email": "julie@acme.fr",
    "date_entretien": "2026-12-01", "heure": "14h", "format": "visio",
    "a_faire": "Confirmer le créneau", "resume": "ACME propose un entretien.",
}


def test_reply_updates_existing_application_and_prepares(client, monkeypatch):  # noqa: F811
    calls = _fake_llm(monkeypatch, INTERVIEW)
    other = client.post("/api/applications", json={"title": "Dev", "company": "Globex"}).json()
    app = client.post("/api/applications", json={
        "title": "Data analyst", "company": "Acme", "status": "postule", "url": "https://acme.fr/offre",
    }).json()

    resp = client.post("/api/recruiter-reply", json={"message": "Bonjour, nous souhaitons vous rencontrer…"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] is False
    assert data["prep_error"] is None
    updated = data["application"]
    assert updated["id"] == app["id"]
    assert updated["status"] == "entretien"
    assert updated["next_action_on"] == "2026-12-01"
    assert "Julie Martin" in updated["contact"]
    assert updated["prep"].startswith("## 1. Situation")
    # L'offre a été lue via son lien et sert à l'analyse des compétences.
    assert "Python, SQL" in updated["offer_text"]
    prep_prompt = calls[-1]["messages"][-1]["content"]
    assert "Python, SQL" in prep_prompt
    assert "acme.fr/a-propos" in prep_prompt
    assert "Analyse approfondie des compétences" in prep_prompt
    assert calls[-1]["max_tokens"] == tracking.PREP_MAX_TOKENS
    assert any("Lecture de l'offre" in s for s in data["steps"])

    detail = client.get(f"/api/applications/{app['id']}").json()
    assert detail["events"][0]["kind"] == "reponse_entretien"
    assert "Confirmer le créneau" in detail["events"][0]["summary"]
    assert client.get(f"/api/applications/{other['id']}").json()["events"] == []


def test_reply_creates_application_when_unknown(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, INTERVIEW | {"entreprise": "Initech"})
    data = client.post("/api/recruiter-reply", json={
        "message": "Bonjour…", "offer_text": "Missions : reporting",
    }).json()
    assert data["created"] is True
    assert data["application"]["company"] == "Initech"
    assert data["application"]["title"] == "Data analyst"
    assert data["application"]["offer_text"] == "Missions : reporting"


def test_refusal_closes_without_preparation(client, monkeypatch):  # noqa: F811
    calls = _fake_llm(monkeypatch, {"type_reponse": "refus", "entreprise": "Acme", "resume": "Candidature non retenue."})
    app = client.post("/api/applications", json={
        "title": "Data analyst", "company": "ACME", "status": "entretien", "next_action_on": "2026-12-01",
    }).json()
    data = client.post("/api/recruiter-reply", json={"message": "Nous sommes au regret…"}).json()
    assert data["application"]["next_action_on"] == ""
    assert data["application"]["id"] == app["id"]
    assert data["application"]["status"] == "refuse"
    assert data["application"]["prep"] == ""
    assert len(calls) == 1


def test_prep_failure_keeps_tracking_sheet(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, INTERVIEW)

    async def no_quota(*args, **kwargs):
        raise llm.LLMError("Limite Groq atteinte")

    monkeypatch.setattr(tracking, "prepare", no_quota)
    data = client.post("/api/recruiter-reply", json={"message": "Bonjour…"}).json()
    assert data["prep_error"] == "Limite Groq atteinte"
    assert data["application"]["status"] == "entretien"


def test_prepare_endpoint_and_unknown_application(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, INTERVIEW)
    app = client.post("/api/applications", json={"title": "Data analyst", "company": "Acme", "offer_text": "SQL"}).json()
    resp = client.post(f"/api/applications/{app['id']}/prepare")
    assert resp.status_code == 200
    assert resp.json()["application"]["prep_updated_on"]
    assert client.post("/api/applications/999/prepare").status_code == 404
    assert client.post("/api/recruiter-reply", json={"message": "x", "application_id": 999}).status_code == 404


def test_find_application_prefers_exact_and_open():
    apps = [
        {"id": 1, "company": "Acme Group", "title": "Stage", "status": "refuse"},
        {"id": 2, "company": "ACME", "title": "Data analyst", "status": "postule"},
        {"id": 3, "company": "Globex", "title": "Data analyst", "status": "postule"},
    ]
    assert tracking.find_application(apps, "Acme SAS", "Data analyst")["id"] == 2
    assert tracking.find_application(apps, "Initech", "") is None
    assert tracking.find_application(apps, "", "Data analyst") is None


def test_old_database_is_migrated(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE applications (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, company TEXT, created_on TEXT)")
    conn.execute("INSERT INTO applications (title, company) VALUES ('Dev', 'Acme')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("HELPER_DB_PATH", str(path))
    db.init_db()
    app = db.update_application(1, {"prep": "fiche", "offer_text": "SQL"})
    assert app["prep"] == "fiche" and app["title"] == "Dev"


def test_new_interview_not_attached_to_other_closed_job():
    apps = [{"id": 1, "company": "Groupe Decathlon Retail", "title": "Chargé de communication", "status": "refuse"}]
    assert tracking.find_application(apps, "Decathlon", "Assistant(e) marketing digital en alternance") is None
    # Même poste : on reprend bien la fiche, même close.
    assert tracking.find_application(apps, "Decathlon", "Chargée de communication")["id"] == 1


def test_ambiguous_company_with_several_open_jobs():
    apps = [
        {"id": 1, "company": "Capgemini", "title": "Développeur Python junior", "status": "postule"},
        {"id": 2, "company": "Capgemini", "title": "Data engineer", "status": "postule"},
    ]
    assert tracking.find_application(apps, "Capgemini", "Développeur Python")["id"] == 1
    assert tracking.find_application(apps, "Capgemini", "Chef de projet") is None
    # Une seule candidature en cours : on la reprend même si l'intitulé diffère.
    assert tracking.find_application(apps[:1], "Capgemini", "Software engineer")["id"] == 1


def test_deadline_becomes_next_action(client, monkeypatch):  # noqa: F811
    _fake_llm(monkeypatch, {"type_reponse": "test", "entreprise": "Capgemini", "poste": "Dev",
                            "date_limite": "2026-12-03", "date_entretien": "pas une date"})
    data = client.post("/api/recruiter-reply", json={"message": "Test à rendre avant le 3/12", "prepare": False}).json()
    assert data["analysis"]["date_entretien"] == ""
    assert data["application"]["next_action_on"] == "2026-12-03"
    assert data["application"]["status"] == "entretien"
