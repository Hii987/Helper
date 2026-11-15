import asyncio
import json

from app import agent, jobs, llm, websearch

DDG_PAGE = """
<div class="result results_links results_links_deep web-result ">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.indeed.fr%2Fviewjob%3Fjk%3D1&amp;rut=abc">Alternance <b>Marketing</b> - Lyon</a>
  </h2>
  <a class="result__snippet" href="#">Entreprise ACME recrute un alternant &amp; plus</a>
</div>
<div class="result results_links web-result ">
  <a class="result__a" href="https://duckduckgo.com/y.js?ad=1">Pub</a>
</div>
<div class="result results_links web-result ">
  <a class="result__a" href="https://www.hellowork.com/fr-fr/emplois/2.html">Assistant marketing</a>
</div>
"""


def test_parse_ddg_results():
    results = websearch.parse_results(DDG_PAGE)
    assert results == [
        {"title": "Alternance Marketing - Lyon", "url": "https://www.indeed.fr/viewjob?jk=1",
         "snippet": "Entreprise ACME recrute un alternant & plus"},
        {"title": "Assistant marketing", "url": "https://www.hellowork.com/fr-fr/emplois/2.html", "snippet": ""},
    ]


def test_job_query_targets_job_sites():
    q = websearch.job_query("marketing", "Lyon", "alternance")
    assert q.startswith("offre alternance marketing Lyon")
    assert "site:indeed.fr" in q


def test_html_to_text():
    title, text = websearch.html_to_text(
        "<html><head><title>Offre</title><style>x{}</style></head>"
        "<body><nav>menu</nav><h1>Développeur</h1><p>CDI à Lyon</p><script>bad()</script></body></html>"
    )
    assert title == "Offre"
    assert "Développeur" in text and "CDI à Lyon" in text
    assert "menu" not in text and "bad()" not in text


def test_fetch_page_refuses_local_addresses():
    for url in ("http://localhost:8000/api/profile", "http://127.0.0.1/", "http://192.168.1.1/", "file:///etc/passwd"):
        try:
            asyncio.run(websearch.fetch_page(url))
        except websearch.WebSearchError:
            continue
        raise AssertionError(f"{url} aurait dû être refusée")


def test_agent_calls_web_search_then_answers(monkeypatch):
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_ID", raising=False)
    calls = []

    async def fake_complete(messages, temperature=0.5, tools=None):
        calls.append((messages, tools))
        if len(calls) == 1:
            return {"content": "", "tool_calls": [{
                "id": "call1",
                "function": {"name": "rechercher_offres_web",
                             "arguments": json.dumps({"mots_cles": "marketing", "lieu": "Lyon", "type": "alternance"})},
            }]}
        return {"content": "Voici une offre : Alternance Marketing - Lyon"}

    async def fake_search_jobs(keywords, location="", kind="emploi", max_results=10):
        assert (keywords, location, kind) == ("marketing", "Lyon", "alternance")
        return [{"title": "Alternance Marketing - Lyon", "url": "https://www.indeed.fr/viewjob?jk=1", "snippet": "ACME"}]

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(websearch, "search_jobs", fake_search_jobs)

    result = asyncio.run(agent.run({}, [{"role": "user", "content": "Trouve des alternances marketing à Lyon"}]))

    assert result["text"] == "Voici une offre : Alternance Marketing - Lyon"
    assert result["steps"] == ["Recherche d'offres sur le web : marketing Lyon"]
    assert result["offers"][0]["url"] == "https://www.indeed.fr/viewjob?jk=1"
    # France Travail non configuré : l'outil n'est pas proposé à l'IA.
    tool_names = [t["function"]["name"] for t in calls[0][1]]
    assert "rechercher_offres_france_travail" not in tool_names
    # Le résultat de l'outil est renvoyé à l'IA avec l'identifiant de l'appel.
    tool_msg = calls[1][0][-1]
    assert tool_msg["role"] == "tool" and tool_msg["tool_call_id"] == "call1"
    assert "indeed.fr" in tool_msg["content"]


def test_agent_reports_tool_errors_without_crashing(monkeypatch):
    calls = []

    async def fake_complete(messages, temperature=0.5, tools=None):
        calls.append(messages)
        if len(calls) == 1:
            return {"tool_calls": [{"id": "c", "function": {"name": "recherche_web", "arguments": '{"requete": "x"}'}}]}
        return {"content": "Désolé, la recherche n'a pas marché."}

    async def failing_search(query, max_results=8):
        raise websearch.WebSearchError("bloqué")

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(websearch, "search", failing_search)
    result = asyncio.run(agent.run({}, [{"role": "user", "content": "cherche"}]))
    assert result["steps"] == ["Échec (recherche_web) : bloqué"]
    assert "bloqué" in calls[1][-1]["content"]


def test_agent_offers_france_travail_tool_when_configured(monkeypatch):
    monkeypatch.setattr(jobs, "is_configured", lambda: True)
    assert "rechercher_offres_france_travail" in [t["function"]["name"] for t in agent._tools()]
