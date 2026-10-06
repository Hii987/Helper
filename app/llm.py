"""Client minimal pour l'API de chat de Mistral AI."""

import asyncio
import os
import time

import httpx

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Le plan gratuit de Mistral limite le débit (environ 1 requête par seconde) :
# on espace les requêtes et on réessaie automatiquement en cas de 429.
MIN_INTERVAL = float(os.getenv("MISTRAL_MIN_INTERVAL", "1.2"))
RETRY_DELAYS = (2, 5, 10)
MAX_OUTPUT_TOKENS = 1200

_lock = asyncio.Lock()
_last_call = 0.0


class LLMError(Exception):
    """Erreur lisible renvoyée à l'utilisateur."""


def is_configured() -> bool:
    return bool(os.getenv("MISTRAL_API_KEY"))


async def chat(messages: list[dict], temperature: float = 0.5) -> str:
    """Envoie une liste de messages {role, content} et renvoie la réponse texte."""
    message = await complete(messages, temperature)
    return message.get("content") or ""


async def complete(messages: list[dict], temperature: float = 0.5, tools: list[dict] | None = None) -> dict:
    """Renvoie le message brut de l'assistant (avec éventuels `tool_calls`)."""
    api_key = (os.getenv("MISTRAL_API_KEY") or "").strip().strip("\"'")
    if not api_key:
        raise LLMError(
            "Aucune clé MISTRAL_API_KEY configurée. Crée une clé gratuite sur "
            "https://console.mistral.ai/api-keys puis ajoute-la dans le fichier .env."
        )
    if not api_key.isascii() or " " in api_key:
        raise LLMError(
            "La clé MISTRAL_API_KEY du fichier .env n'est pas valide (elle contient des accents "
            "ou des espaces). Remplace-la par ta vraie clé copiée depuis "
            "https://console.mistral.ai/api-keys, puis redémarre l'application."
        )

    payload = {
        "model": os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
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
        raise LLMError("Clé API Mistral invalide (401).")
    if resp.status_code == 429:
        raise LLMError(
            "Limite Mistral atteinte malgré plusieurs essais. Si ça persiste, ton quota du plan "
            f"gratuit est peut-être épuisé (voir https://console.mistral.ai/usage). Détail : {_detail(resp)}"
        )
    if resp.status_code >= 400:
        raise LLMError(f"Erreur Mistral {resp.status_code} : {_detail(resp)}")

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
                return await client.post(MISTRAL_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"Impossible de contacter Mistral : {exc}") from exc
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
        return str(body.get("message") or body.get("detail") or body)[:300]
    except ValueError:
        return resp.text[:300]
