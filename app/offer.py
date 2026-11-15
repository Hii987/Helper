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


async def summarize(url: str, text: str) -> dict:
    """Résume `text` s'il est fourni, sinon lit la page `url`. Lève WebSearchError ou LLMError."""
    if text.strip():
        source = ""
    else:
        page = await websearch.fetch_page(url, max_chars=MAX_OFFER_CHARS)
        text = page["text"]
        source = _short_url(page["url"])
    text = text.strip()[:MAX_OFFER_CHARS]
    answer = await llm.chat(
        [{"role": "system", "content": PROMPT}, {"role": "user", "content": text}],
        temperature=0, json_mode=True,
    )
    try:
        data = json.loads(answer)
    except ValueError as exc:
        raise llm.LLMError("The AI answer could not be read. Try again.") from exc
    result = {k: str(data.get(k) or "").strip() for k in TEXT_FIELDS}
    for k in LIST_FIELDS:
        items = data.get(k) if isinstance(data.get(k), list) else []
        result[k] = [str(i).strip() for i in items if str(i).strip()]
    return {**result, "rawText": text, "source": source}


def _short_url(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.netloc.removeprefix("www.") + parsed.path).rstrip("/")
