"""Client minimal pour l'API de chat de Mistral AI."""

import os

import httpx

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


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
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(MISTRAL_URL, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise LLMError(f"Impossible de contacter Mistral : {exc}") from exc

    if resp.status_code == 401:
        raise LLMError("Clé API Mistral invalide (401).")
    if resp.status_code == 429:
        raise LLMError("Limite de requêtes Mistral atteinte (plan gratuit). Réessaie dans quelques secondes.")
    if resp.status_code >= 400:
        raise LLMError(f"Erreur Mistral {resp.status_code} : {resp.text[:300]}")

    return resp.json()["choices"][0]["message"]
