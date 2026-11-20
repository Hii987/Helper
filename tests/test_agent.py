import asyncio
import json

import httpx

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


def test_agent_survives_invalid_tool_call(monkeypatch):
    calls = []

    async def fake_complete(messages, temperature=0.5, tools=None):
        calls.append(tools)
        if tools:
            raise llm.ToolCallError("attempted to call tool 'ouvrir_page' which was not in request.tools")
        return {"content": "Réponse sans recherche."}

    monkeypatch.setattr(llm, "complete", fake_complete)
    result = asyncio.run(agent.run({}, [{"role": "user", "content": "cherche"}]))
    assert result["text"] == "Réponse sans recherche."
    assert len(calls) == 3 and calls[-1] is None  # 2 essais avec outils, puis réponse sans outils
    assert "sans recherche" in result["steps"][0]


def test_final_answer_is_requested_without_tool_history(monkeypatch):
    calls = []

    async def fake_complete(messages, temperature=0.5, tools=None):
        calls.append((messages, tools))
        if tools:  # le modèle insiste pour chercher
            return {"content": "", "tool_calls": [{"id": f"c{len(calls)}", "function": {"name": "recherche_web", "arguments": '{"requete": "x"}'}}]}
        return {"content": "Synthèse finale."}

    async def failing_search(query, max_results=8):
        raise websearch.WebSearchError("bloqué")

    monkeypatch.setattr(llm, "complete", fake_complete)
    monkeypatch.setattr(websearch, "search", failing_search)
    result = asyncio.run(agent.run({}, [{"role": "user", "content": "cherche"}]))
    assert result["text"] == "Synthèse finale."
    final_messages, final_tools = calls[-1]
    assert final_tools is None
    assert all(m["role"] != "tool" and not m.get("tool_calls") for m in final_messages)
    assert "bloqué" in final_messages[-1]["content"]


class _FakeClient:
    """Remplace httpx.AsyncClient : enregistre les requêtes et renvoie des réponses préparées."""
    def __init__(self, responses, sent):
        self.responses, self.sent = responses, sent

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        self.sent.append((url, kwargs))
        status, body = self.responses.pop(0)
        request = httpx.Request("POST", url)
        if isinstance(body, str):
            return httpx.Response(status, text=body, request=request)
        return httpx.Response(status, json=body, request=request)


def _fake_http(monkeypatch, responses):
    sent = []
    monkeypatch.setattr(websearch.httpx, "AsyncClient", lambda **kw: _FakeClient(responses, sent))
    return sent


def test_tavily_is_used_when_configured(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    sent = _fake_http(monkeypatch, [(200, {"results": [
        {"title": "Alternance <b>marketing</b>", "url": "https://www.indeed.fr/x", "content": "ACME recrute"},
        {"title": "sans lien"},
    ]})])
    results = asyncio.run(websearch.search_jobs("marketing", "Lille", "alternance", max_results=5))
    assert results == [{"title": "Alternance marketing", "url": "https://www.indeed.fr/x", "snippet": "ACME recrute"}]
    url, kwargs = sent[0]
    assert url == websearch.TAVILY_URL
    assert kwargs["headers"]["Authorization"] == "Bearer tvly-test"
    assert kwargs["json"]["query"] == "offre alternance marketing Lille"
    assert "linkedin.com" in kwargs["json"]["include_domains"] and "indeed.fr" in kwargs["json"]["include_domains"]


def test_duckduckgo_takes_over_when_tavily_fails(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    sent = _fake_http(monkeypatch, [(432, {}), (200, DDG_PAGE)])
    results = asyncio.run(websearch.search("entreprise ACME"))
    assert [u for u, _ in sent] == [websearch.TAVILY_URL, websearch.DDG_URL]
    assert results[0]["url"] == "https://www.indeed.fr/viewjob?jk=1"


def test_clear_errors(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    _fake_http(monkeypatch, [(202, "")])
    try:
        asyncio.run(websearch.search("x"))
    except websearch.WebSearchError as exc:
        assert "TAVILY_API_KEY" in str(exc)
    else:
        raise AssertionError("DuckDuckGo bloqué aurait dû lever une erreur")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-bad")
    _fake_http(monkeypatch, [(401, {}), (202, "")])
    try:
        asyncio.run(websearch.search("x"))
    except websearch.WebSearchError as exc:
        assert "invalide" in str(exc)  # l'erreur Tavily est plus utile que celle de DuckDuckGo
