"""Lecture d'une offre d'emploi et résumé en points clés par l'IA."""

import json
from urllib.parse import urlparse

from . import llm, websearch

MAX_OFFER_CHARS = 12000
TEXT_FIELDS = ("company", "jobTitle", "contract", "salary", "workMode", "experience", "start")
LIST_FIELDS = ("responsibilities", "requirements")

PROMPT = """Extract the key points of this job offer. Answer with a JSON object with exactly these keys:
company, jobTitle, contract, salary, workMode, experience, start (short strings),
responsibilities, requirements (arrays of short strings, at most 6 each).
Write the values in the language of the offer. If the offer does not state something,
use an empty string or an empty array: never guess or invent a value."""

COMPANY_PROMPT = """Using the job offer and the web search results given, summarize in 2 to 4 sentences
what the company "{company}" does: its activity, products or services, and sector.
Answer with a JSON object with exactly one key: summary (a string).
Write in the language of the offer. Only use facts from the texts given: never guess or invent.
If they say nothing about the company, use an empty string."""


async def summarize(url: str, text: str, with_company: bool = False) -> dict:
    """Résume `text` s'il est fourni, sinon lit la page `url`. Lève WebSearchError ou LLMError.

    Avec `with_company`, ajoute un résumé de l'entreprise (offre + recherche web)."""
    if text.strip():
        source = ""
    else:
        page = await websearch.fetch_page(url, max_chars=MAX_OFFER_CHARS)
        text = page["text"]
        source = _short_url(page["url"])
    text = text.strip()[:MAX_OFFER_CHARS]
    data = await _ask_json(PROMPT, text)
    result = {k: str(data.get(k) or "").strip() for k in TEXT_FIELDS}
    for k in LIST_FIELDS:
        items = data.get(k) if isinstance(data.get(k), list) else []
        result[k] = [str(i).strip() for i in items if str(i).strip()]
    company = ""
    if with_company and result["company"]:
        company = await _company_summary(result["company"], text)
    return {**result, "companySummary": company, "rawText": text, "source": source}


async def _company_summary(company: str, offer_text: str) -> str:
    try:  # la recherche web complète l'offre ; sans elle, on se contente de l'offre
        results = await websearch.search(company, max_results=5)
    except websearch.WebSearchError:
        results = []
    found = "\n".join(f"- {r['title']}: {r['snippet']}" for r in results)
    data = await _ask_json(COMPANY_PROMPT.format(company=company),
                           f"Job offer:\n{offer_text}\n\nWeb search results:\n{found}")
    return str(data.get("summary") or "").strip()


async def _ask_json(prompt: str, content: str) -> dict:
    answer = await llm.chat(
        [{"role": "system", "content": prompt}, {"role": "user", "content": content}],
        temperature=0, json_mode=True,
    )
    try:
        return json.loads(answer)
    except ValueError as exc:
        raise llm.LLMError("The AI answer could not be read. Try again.") from exc


def _short_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc.removeprefix("www.") + parsed.path).rstrip("/")
