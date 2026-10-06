"""Client minimal pour l'API de chat de Groq (compatible OpenAI)."""

import asyncio
import os
import time

import httpx

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Le plan gratuit de Groq limite le débit (environ 30 requêtes par minute) :
# on espace les requêtes et on réessaie automatiquement en cas de 429.
MIN_INTERVAL = float(os.getenv("GROQ_MIN_INTERVAL", "2.1"))
RETRY_DELAYS = (2, 5, 10)
MAX_OUTPUT_TOKENS = 1200

_lock = asyncio.Lock()
_last_call = 0.0


class LLMError(Exception):
    """Erreur lisible renvoyée à l'utilisateur."""


def is_configured() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))


async def chat(messages: list[dict], temperature: float = 0.5) -> str:
    """Envoie une liste de messages {role, content} et renvoie la réponse texte."""
    message = await complete(messages, temperature)
    return message.get("content") or ""


async def complete(messages: list[dict], temperature: float = 0.5, tools: list[dict] | None = None) -> dict:
    """Renvoie le message brut de l'assistant (avec éventuels `tool_calls`)."""
    api_key = (os.getenv("GROQ_API_KEY") or "").strip().strip("\"'")
    if not api_key:
        raise LLMError(
            "Aucune clé GROQ_API_KEY configurée. Crée une clé gratuite sur "
            "https://console.groq.com/keys puis ajoute-la dans le fichier .env."
        )
    if not api_key.isascii() or " " in api_key:
        raise LLMError(
            "La clé GROQ_API_KEY du fichier .env n'est pas valide (elle contient des accents "
            "ou des espaces). Remplace-la par ta vraie clé copiée depuis "
            "https://console.groq.com/keys, puis redémarre l'application."
        )

    payload = {
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": MAX_OUTPUT_TOKENS,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {api_key}"}

    for attempt in range(len(RETRY_DELAYS) + 1):
        resp = await _post(payload, headers)
        if resp.status_code != 429 or attempt == len(RETRY_DELAYS):
            break
        await asyncio.sleep(_retry_after(resp) or RETRY_DELAYS[attempt])

    if resp.status_code == 401:
        raise LLMError("Clé API Groq invalide (401).")
    if resp.status_code == 429:
        raise LLMError(
            "Limite Groq atteinte malgré plusieurs essais. Si ça persiste, ton quota du plan "
            f"gratuit est peut-être épuisé (voir https://console.groq.com/settings/limits). Détail : {_detail(resp)}"
        )
    if resp.status_code == 413:
        raise LLMError(
            "Requête trop volumineuse pour le plan gratuit Groq (limite de tokens par minute). "
            f"Raccourcis ton message ou ton CV, ou change de modèle via GROQ_MODEL. Détail : {_detail(resp)}"
        )
    if resp.status_code >= 400:
        raise LLMError(f"Erreur Groq {resp.status_code} : {_detail(resp)}")

    data = resp.json()
    message = dict(data["choices"][0]["message"])
    message["usage"] = data.get("usage") or {}
    return message


async def _post(payload: dict, headers: dict) -> httpx.Response:
    """Envoie la requête en respectant un délai minimal entre deux appels."""
    global _last_call
    async with _lock:
        wait = _last_call + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                return await client.post(GROQ_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"Impossible de contacter Groq : {exc}") from exc
        finally:
            _last_call = time.monotonic()


def _retry_after(resp: httpx.Response) -> float:
    try:
        return min(float(resp.headers.get("retry-after", 0)), 30)
    except ValueError:
        return 0


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        error = body.get("error")
        if isinstance(error, dict):
            error = error.get("message")
        return str(error or body.get("message") or body.get("detail") or body)[:300]
    except ValueError:
        return resp.text[:300]
