import asyncio
import json

import httpx

from app import companies, llm, websearch

from .test_app import client  # noqa: F401  (fixture)

CENTER = {"label": "Lille", "lat": 50.6309, "lon": 3.0454}


def _company(name, siren, *, lat=50.632, lon=3.05, size="12", state="A", site_state="A", employer="O", naf="73.11Z"):
    return {
        "siren": siren, "nom_complet": name, "activite_principale": naf, "tranche_effectif_salarie": size,
        "etat_administratif": state, "statut_diffusion": "O", "caractere_employeur": employer,
        "matching_etablissements": [{
            "etat_administratif": site_state, "latitude": str(lat), "longitude": str(lon), "adresse": "1 RUE X 59000 LILLE",
            "libelle_commune": "LILLE", "tranche_effectif_salarie": size, "est_siege": True, "nom_commercial": None,
            "liste_enseignes": None,
        }],
    }


def test_to_result_filters_and_names():
    ok = companies.to_result(_company("TRUSTTEAM (TRUSTTEAM)", "1"), CENTER, 10, 10)
    assert ok["name"] == "Trustteam" and ok["activityLabel"] == "Activités des agences de publicité"
    assert 0 < ok["distanceKm"] < 1
    assert companies.to_result(_company("Fermée", "2", state="C"), CENTER, 10, 1) is None
    assert companies.to_result(_company("Établissement fermé", "3", site_state="F"), CENTER, 10, 1) is None
    assert companies.to_result(_company("Trop petite", "4", size="02"), CENTER, 10, 10) is None
    assert companies.to_result(_company("Loin", "5", lat=50.9), CENTER, 10, 1) is None
    assert companies.to_result(_company("Sans salarié", "6", size="NN", employer="N"), CENTER, 10, 1) is None
    assert companies.to_result(_company("Sans salarié", "6", size="NN", employer="N"), CENTER, 10, 0) is not None


def test_choose_activities_validates_and_reranks(monkeypatch):
    calls = []

    async def fake_chat(messages, temperature=0.5, max_tokens=None, json_mode=False):
        calls.append(messages[-1]["content"])
        if len(calls) == 1:  # propositions libres : un code inventé, un hors sujet
            return json.dumps({"activites": [{"code": "71.12B"}, {"code": "99.99X"}, {"code": "69.20Z"}]})
        return json.dumps({"codes": ["69.20Z", "12.34Z"]})

    monkeypatch.setattr(llm, "chat", fake_chat)
    acts = asyncio.run(companies.choose_activities("comptable"))
    assert acts == [{"code": "69.20Z", "label": "Activités comptables"}]
    # Le tri voit les libellés officiels ; le code inventé n'y figure pas.
    assert "69.20Z : Activités comptables" in calls[1] and "99.99X" not in calls[1]


class _FakeClient:
    def __init__(self, routes, seen):
        self.routes, self.seen = routes, seen

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.seen.append((url, dict(params or {})))
        body = self.routes[url](params or {})
        return httpx.Response(200, json=body, request=httpx.Request("GET", url))


def _fake_apis(monkeypatch, pages):
    seen = []
    routes = {
        companies.GEOCODE_URL: lambda p: {"features": [{"geometry": {"coordinates": [3.0454, 50.6309]}, "properties": {"label": "Lille"}}]}
        if p.get("q") != "Nowhere" else {"features": []},
        companies.COMPANIES_URL: lambda p: {"results": pages.get(p["page"], []), "total_pages": 5, "total_results": 120},
    }
    monkeypatch.setattr(companies.httpx, "AsyncClient", lambda **kw: _FakeClient(routes, seen))
    return seen


def test_search_endpoint(client, monkeypatch):  # noqa: F811
    async def fake_choose(what):
        return [{"code": "73.11Z", "label": "Activités des agences de publicité"}, {"code": "70.21Z", "label": "Conseil en relations publiques et communication"}]

    monkeypatch.setattr(companies, "choose_activities", fake_choose)
    seen = _fake_apis(monkeypatch, {
        1: [_company("Proche RP", "1", naf="70.21Z", lat=50.631), _company("Agence loin", "2", lat=50.68)],
        2: [_company("Agence proche", "3", lat=50.632), _company("Proche RP", "1", naf="70.21Z")],
        3: [_company("Petite", "4", size="01")],
    })
    data = client.post("/api/companies/search", json={"what": "marketing", "where": "Lille", "radius": 10, "minSize": 10}).json()
    assert [r["name"] for r in data["results"]] == ["Agence proche", "Agence loin", "Proche RP"]  # secteur puis distance
    assert data["hasMore"] is True and data["center"]["label"] == "Lille"
    params = seen[1][1]
    assert params["activite_principale"] == "73.11Z,70.21Z" and params["radius"] == 10 and params["page"] == 1
    assert [p["page"] for _, p in seen[1:]] == [1, 2, 3]

    # Page suivante avec les secteurs déjà choisis : pas de nouvel appel à l'IA, codes vérifiés.
    monkeypatch.setattr(companies, "choose_activities", None)
    seen.clear()
    data = client.post("/api/companies/search", json={"what": "marketing", "where": "Lille", "page": 2,
                                                      "activities": ["70.21Z", "00.00X"], "radius": 80}).json()
    assert data["activities"] == [{"code": "70.21Z", "label": "Conseil en relations publiques et communication"}]
    assert [p["page"] for _, p in seen[1:]] == [4, 5]  # s'arrête à la dernière page de l'annuaire
    assert seen[1][1]["radius"] == 50  # limite de l'API

    assert client.post("/api/companies/search", json={"what": "x", "where": "Nowhere", "activities": ["70.21Z"]}).status_code == 422
    assert client.post("/api/companies/search", json={"what": " ", "where": "Lille"}).status_code == 400


HOME = """<html><head><title>Agence Lumen</title></head><body>
<nav><a href="/contact">Contact</a> <a href="/nous-rejoindre/">Nous rejoindre</a> <a href="https://facebook.com/lumen">fb</a>
<a href="/blog/article">Blog</a></nav><p>Agence de communication digitale à Lille depuis 2010.</p>
<footer>hello [at] agence-lumen.fr · <img src="logo@2x.png"></footer></body></html>"""
CONTACT = '<a href="mailto:contact@agence-lumen.fr">Écrire</a> camille.durand@agence-lumen.fr support@wixpress.com'
JOIN = "Envoie ta candidature à recrutement&#64;agence-lumen.fr ou jobs@gmail.com"


def test_find_contact(monkeypatch):
    async def fake_search(query, max_results=8, domains=()):
        assert query == "Agence Lumen Lille"
        return [{"title": "Agence Lumen", "url": "https://tavily.com/knowledge/company/abc"},
                {"title": "AGENCE LUMEN - Societe.com", "url": "https://www.societe.com/societe/agence-lumen-1.html"},
                {"title": "Agence Lumen | Communication digitale", "url": "https://www.agence-lumen.fr/accueil"}]

    pages = {"https://www.agence-lumen.fr/": HOME, "https://www.agence-lumen.fr/contact": CONTACT,
             "https://www.agence-lumen.fr/nous-rejoindre/": JOIN}

    async def fake_fetch(url, timeout=20):
        if url not in pages:
            raise websearch.WebSearchError("404")
        return url, pages[url]

    monkeypatch.setattr(websearch, "search", fake_search)
    monkeypatch.setattr(websearch, "fetch_html", fake_fetch)
    found = asyncio.run(companies.find_contact("Agence Lumen", "Lille"))
    assert found["website"] == "https://www.agence-lumen.fr/"
    assert found["careersUrl"] == "https://www.agence-lumen.fr/nous-rejoindre/"
    assert [(e["email"], e["kind"]) for e in found["emails"]] == [
        ("recrutement@agence-lumen.fr", "recruiting"), ("contact@agence-lumen.fr", "generic"),
        ("hello@agence-lumen.fr", "generic"), ("camille.durand@agence-lumen.fr", "named"),
    ]  # l'adresse gmail et les adresses parasites sont écartées
    assert "communication digitale" in found["description"] and found["pages"] == 3


def test_find_contact_without_website(monkeypatch):
    queries = []

    async def directories_only(query, max_results=8, domains=()):
        queries.append(query)
        return [{"title": "X - Pappers", "url": "https://www.pappers.fr/entreprise/x"},
                {"title": "Umt", "url": "https://umet.univ-lille.fr"}]

    monkeypatch.setattr(websearch, "search", directories_only)
    assert asyncio.run(companies.find_contact("Umt", "Lille"))["website"] == ""
    assert queries == ["Umt Lille", "Umt site web entreprise"]  # seconde formulation tentée


def test_pick_website_real_cases():
    # Résultats réels de Tavily (novembre 2026) : sa propre fiche et des agrégateurs titrent avec le nom.
    ef = [{"url": "https://tavily.com/knowledge/company/gcm07e3iTOLm", "title": "EF INTERNATIONAL"},
          {"url": "https://www.ef.com/wwen", "title": "EF - Language. Education. Travel."},
          {"url": "https://www.ef.fr", "title": "EF - Langue. Éducation. Voyage. | EF France"},
          {"url": "https://www.efacademy.org/en", "title": "International Boarding Schools"}]
    assert companies.pick_website(ef, "Ef International") == "https://www.ef.fr/"
    carre = [{"url": "https://tracxn.com/d/companies/carr-noir/x", "title": "Carré Noir - Company Profile"},
             {"url": "https://rocketreach.co/carre-noir-profile_b5", "title": "Carré Noir Information"},
             {"url": "https://www.ville-wasquehal.fr", "title": "Accueil - Ville de Wasquehal"}]
    assert companies.pick_website(carre, "Carre Noir") == ""
    sopra = [{"url": "https://www.soprasteria.com/", "title": "Sopra Steria"},
             {"url": "https://www.soprahr.com/fr", "title": "Sopra HR Software"}]
    assert companies.pick_website(sopra, "Sopra Hr Software") == "https://www.soprahr.com/"
    havas = [{"url": "https://havasmedianetwork.com", "title": "Havas Media Network"},
             {"url": "https://www.havas.fr", "title": "Havas: Growth, Powered by Desire"}]
    # Le site qui reprend le plus de mots du nom (Havas + Media) l'emporte sur celui du groupe.
    assert companies.pick_website(havas, "Havas Media France") == "https://havasmedianetwork.com/"
    assert companies.pick_website(havas, "Havas") == "https://www.havas.fr/"


def test_contact_and_application_endpoints(client, monkeypatch):  # noqa: F811
    async def blocked(query, max_results=8, domains=()):
        raise websearch.WebSearchError("DuckDuckGo bloque…")

    monkeypatch.setattr(websearch, "search", blocked)
    resp = client.post("/api/companies/contact", json={"name": "X", "city": "Lille"})
    assert resp.status_code == 422 and "DuckDuckGo" in resp.json()["detail"]

    prompts_seen = []

    async def fake_chat(messages, temperature=0.5, max_tokens=None, json_mode=False):
        prompts_seen.append(messages)
        return json.dumps({"objet": "Candidature spontanée", "corps": "Bonjour…"})

    monkeypatch.setattr(llm, "chat", fake_chat)
    client.put("/api/profile", json={"cv": "Stage chez Bike&Co"})
    data = client.post("/api/companies/application", json={
        "company": {"name": "Agence Lumen", "city": "Lille", "activityLabel": "Agences de publicité"},
        "what": "alternance marketing", "description": "Agence de communication digitale", "lang": "en"}).json()
    assert data == {"subject": "Candidature spontanée", "body": "Bonjour…"}
    system, user = prompts_seen[0][0]["content"], prompts_seen[0][-1]["content"]
    assert "Bike&Co" in system and "Agence Lumen" in user and "communication digitale" in user
    assert user.endswith("Always answer in English.")
