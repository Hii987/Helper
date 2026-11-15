"""Suivi automatique des réponses de recruteurs et préparation des entretiens.

À chaque message de recruteur collé dans l'appli :
1. l'IA en extrait les informations (type de réponse, date d'entretien, contact…) ;
2. la fiche de suivi correspondante est retrouvée, ou créée, puis mise à jour ;
3. si la candidature avance, une fiche de préparation d'entretien est générée :
   recherches web sur l'entreprise + analyse détaillée des compétences demandées.
"""

import asyncio
import json
import re
import unicodedata
from datetime import date

from . import db, llm, prompts, websearch

PREP_MAX_TOKENS = 4500
MAX_SNIPPET = 300

# Statut de la candidature selon le type de réponse reçue.
STATUS_FOR_REPLY = {"entretien": "entretien", "test": "entretien", "offre": "offre", "refus": "refuse"}
CLOSED = ("offre", "refuse")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\b(sas|sa|sarl|group|groupe|france)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _parse_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        data = {}
    return {k: str(v).strip() for k, v in data.items() if v is not None} if isinstance(data, dict) else {}


STOPWORDS = {"de", "du", "des", "en", "et", "la", "le", "les", "un", "une", "h", "f", "e", "a", "au", "pour"}


def _title_similarity(a: str, b: str) -> float:
    """Part des mots significatifs du poste le plus court présents dans l'autre (0 à 1)."""
    wa = {w for w in _normalize(a).split() if w not in STOPWORDS}
    wb = {w for w in _normalize(b).split() if w not in STOPWORDS}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def find_application(applications: list[dict], company: str, title: str) -> dict | None:
    """Retrouve la candidature qui correspond le mieux à l'entreprise (et au poste).

    Une candidature close (refus, offre) n'est reprise que si le poste correspond aussi :
    une nouvelle invitation chez la même entreprise concerne souvent un autre poste.
    Si le poste est connu et ne correspond à aucune candidature de l'entreprise,
    on ne rattache qu'à une candidature en cours unique.
    """
    target = _normalize(company)
    if not target:
        return None
    candidates = []
    for app in applications:
        name = _normalize(app.get("company", ""))
        if not name or not (name == target or name in target or target in name):
            continue
        same_title = bool(title) and _title_similarity(title, app.get("title", "")) >= 0.5
        if app.get("status") in CLOSED and not same_title:
            continue
        score = (2 if name == target else 1) + (2 if same_title else 0) + (1 if app.get("status") not in CLOSED else 0)
        candidates.append((score, same_title, app))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    score, same_title, best = candidates[0]
    if title and not same_title and len(candidates) > 1:
        return None  # plusieurs candidatures en cours, aucune pour ce poste : on ne devine pas
    return best


async def analyze_reply(message: str) -> dict:
    known = "; ".join(
        f"{a['company']} ({a['title']})" for a in db.list_applications() if a.get("company")
    )[:1500]
    raw = await llm.chat(
        prompts.recruiter_reply_messages(message, date.today().isoformat(), known),
        temperature=0.1, json_mode=True,
    )
    info = _parse_json(raw)
    if info.get("type_reponse") not in prompts.REPLY_TYPES:
        info["type_reponse"] = "autre"
    for key in ("date_entretien", "date_limite"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", info.get(key, "")):
            info[key] = ""
    return info


def situation_text(info: dict) -> str:
    parts = [
        info.get("resume", ""),
        f"Type : {info.get('type_reponse', '')}",
        f"Date : {info.get('date_entretien', '')} {info.get('heure', '')}".strip(),
        f"Échéance : {info.get('date_limite', '')}",
        f"Format : {info.get('format', '')} {info.get('lieu_ou_lien', '')}".strip(),
        f"Interlocuteurs : {info.get('interlocuteurs', '')}",
        f"À faire : {info.get('a_faire', '')}",
    ]
    return "\n".join(p for p in parts if p and not p.endswith(":"))


async def record_reply(message: str, app_id: int | None = None, offer_text: str = "") -> tuple[dict, dict, bool]:
    """Analyse le message et crée / met à jour la fiche de suivi. Renvoie (fiche, infos, créée ?)."""
    info = await analyze_reply(message)
    app = db.get_application(app_id) if app_id else None
    if app_id and app is None:
        raise LookupError("Candidature introuvable.")
    if app is None:
        app = find_application(db.list_applications(), info.get("entreprise", ""), info.get("poste", ""))

    created = app is None
    if created:
        app = db.create_application({
            "title": info.get("poste") or "Poste à préciser",
            "company": info.get("entreprise", ""),
            "status": "postule",
        })

    contact = ", ".join(
        x for x in (info.get("contact_nom"), info.get("contact_role"), info.get("contact_email")) if x
    )
    updates = {}
    status = STATUS_FOR_REPLY.get(info["type_reponse"])
    if status:
        updates["status"] = status
    elif app["status"] == "a_postuler":
        updates["status"] = "postule"
    if contact:
        updates["contact"] = contact
    if info["type_reponse"] == "refus":
        updates["next_action_on"] = ""  # plus rien à faire pour cette candidature
    elif info["date_entretien"]:
        updates["next_action_on"] = info["date_entretien"]
    elif info["date_limite"] and info["type_reponse"] != "refus":
        updates["next_action_on"] = info["date_limite"]
    elif info.get("a_faire") and info["type_reponse"] != "refus":
        updates["next_action_on"] = date.today().isoformat()
    if not app.get("title") or app["title"] == "Poste à préciser":
        if info.get("poste"):
            updates["title"] = info["poste"]
    if offer_text.strip():
        updates["offer_text"] = offer_text.strip()
    app = db.update_application(app["id"], updates)
    db.add_event(app["id"], f"reponse_{info['type_reponse']}", situation_text(info), message)
    return app, info, created


async def research_company(company: str) -> tuple[str, list[str]]:
    """Recherches web sur l'entreprise ; renvoie (texte pour l'IA, étapes lisibles)."""
    if not company.strip():
        return "", []
    queries = (
        f"{company} entreprise activité chiffres clés",
        f"{company} actualités recrutement culture avis salariés",
    )
    results = await asyncio.gather(*(websearch.search(q, max_results=5) for q in queries), return_exceptions=True)
    lines, steps, seen = [], [], set()
    for query, found in zip(queries, results):
        if isinstance(found, Exception):
            steps.append(f"Échec de la recherche « {query} » : {found}")
            continue
        steps.append(f"Recherche web : {query}")
        for r in found:
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            lines.append(f"- {r['title']} ({r['url']}) : {r.get('snippet', '')[:MAX_SNIPPET]}")
    return "\n".join(lines)[: prompts.MAX_RESEARCH], steps


async def prepare(app_id: int, situation: str = "") -> tuple[dict, list[str]]:
    """Génère et enregistre la fiche de préparation d'entretien d'une candidature."""
    app = db.get_application(app_id)
    if app is None:
        raise LookupError("Candidature introuvable.")
    steps: list[str] = []

    if not app.get("offer_text") and app.get("url"):
        try:
            page = await websearch.fetch_page(app["url"], max_chars=prompts.MAX_OFFER_TEXT)
            if page.get("text"):
                app = db.update_application(app_id, {"offer_text": page["text"]})
                steps.append(f"Lecture de l'offre : {page.get('title') or app['url']}")
        except websearch.WebSearchError as exc:
            steps.append(f"Offre illisible ({exc}) : colle son texte dans la fiche pour une analyse plus précise.")

    research, research_steps = await research_company(app.get("company", ""))
    steps += research_steps

    if not situation:
        events = db.list_events(app_id)
        situation = events[0]["summary"] if events else ""

    prep = await llm.chat(
        prompts.interview_prep_messages(db.get_profile(), app, situation, research),
        temperature=0.4, max_tokens=PREP_MAX_TOKENS,
    )
    app = db.update_application(app_id, {"prep": prep, "prep_updated_on": date.today().isoformat()})
    return app, steps
