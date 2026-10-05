"""Recherche d'offres via l'API Offres d'emploi v2 de France Travail.

Sans identifiants, on renvoie des liens de recherche prêts à l'emploi vers
les principaux sites d'offres.
"""

import os
import time
from urllib.parse import quote_plus

import httpx

TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
SCOPE = "api_offresdemploiv2 o2dsoffre"

KINDS = ("emploi", "stage", "alternance")

_token_cache: dict = {"value": None, "expires": 0.0}


class JobSearchError(Exception):
    pass


def is_configured() -> bool:
    return bool(os.getenv("FRANCE_TRAVAIL_CLIENT_ID") and os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET"))


def external_links(keywords: str, location: str, kind: str) -> list[dict]:
    """Liens de recherche vers des sites d'offres (utilisables sans clé API)."""
    words = keywords.strip()
    if kind == "stage" and "stage" not in words.lower():
        words = f"stage {words}".strip()
    if kind == "alternance" and "alternance" not in words.lower():
        words = f"alternance {words}".strip()
    q, loc = quote_plus(words), quote_plus(location.strip())
    links = [
        {"name": "France Travail", "url": f"https://candidat.francetravail.fr/offres/recherche?motsCles={q}"},
        {"name": "Indeed", "url": f"https://fr.indeed.com/jobs?q={q}&l={loc}"},
        {"name": "Welcome to the Jungle", "url": f"https://www.welcometothejungle.com/fr/jobs?query={q}"},
        {"name": "LinkedIn", "url": f"https://www.linkedin.com/jobs/search/?keywords={q}&location={loc}"},
    ]
    if kind == "alternance":
        links.insert(0, {"name": "La bonne alternance", "url": "https://labonnealternance.apprentissage.beta.gouv.fr/recherche"})
    if kind in ("stage", "alternance"):
        links.append({"name": "1jeune1solution", "url": f"https://www.1jeune1solution.gouv.fr/{'apprentissage' if kind == 'alternance' else 'stages'}?q={q}"})
    return links


async def _get_token(client: httpx.AsyncClient) -> str:
    if _token_cache["value"] and _token_cache["expires"] > time.time() + 30:
        return _token_cache["value"]
    resp = await client.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.getenv("FRANCE_TRAVAIL_CLIENT_ID"),
            "client_secret": os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET"),
            "scope": SCOPE,
        },
    )
    if resp.status_code != 200:
        raise JobSearchError(f"Authentification France Travail refusée ({resp.status_code}).")
    data = resp.json()
    _token_cache["value"] = data["access_token"]
    _token_cache["expires"] = time.time() + int(data.get("expires_in", 1499))
    return _token_cache["value"]


def _normalize(offer: dict) -> dict:
    lieu = offer.get("lieuTravail") or {}
    entreprise = offer.get("entreprise") or {}
    origine = offer.get("origineOffre") or {}
    salaire = offer.get("salaire") or {}
    return {
        "id": offer.get("id", ""),
        "title": offer.get("intitule", ""),
        "company": entreprise.get("nom", ""),
        "location": lieu.get("libelle", ""),
        "contract_type": offer.get("typeContratLibelle") or offer.get("typeContrat", ""),
        "alternance": bool(offer.get("alternance")),
        "salary": salaire.get("libelle", ""),
        "published": (offer.get("dateCreation") or "")[:10],
        "description": offer.get("description", ""),
        "url": origine.get("urlOrigine")
        or f"https://candidat.francetravail.fr/offres/recherche/detail/{offer.get('id', '')}",
    }


async def search(keywords: str, department: str = "", kind: str = "emploi", limit: int = 20) -> list[dict]:
    """Recherche d'offres. `department` : numéro de département (ex. 75, 69, 2A)."""
    params = {"range": f"0-{max(1, min(limit, 50)) - 1}"}
    words = keywords.strip()
    if kind == "stage":
        words = f"stage {words}".strip()
    if words:
        params["motsCles"] = words
    if department.strip():
        params["departement"] = department.strip()
    if kind == "alternance":
        params["natureContrat"] = "E2,FS"  # contrat d'apprentissage, contrat de professionnalisation

    async with httpx.AsyncClient(timeout=30) as client:
        token = await _get_token(client)
        resp = await client.get(SEARCH_URL, params=params, headers={"Authorization": f"Bearer {token}"})

    if resp.status_code == 204:
        return []
    if resp.status_code not in (200, 206):
        raise JobSearchError(f"Erreur France Travail {resp.status_code} : {resp.text[:200]}")
    return [_normalize(o) for o in resp.json().get("resultats", [])]
