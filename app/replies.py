"""Réponses de recruteurs et préparation des entretiens.

À chaque message de recruteur collé dans l'appli :
1. l'IA en extrait les informations (type de réponse, date d'entretien, échéance, contact…) ;
2. la candidature correspondante est retrouvée (ou créée) : statut, prochaine étape,
   contact et historique des échanges sont mis à jour ;
3. si la candidature avance, l'interface demande la préparation d'entretien :
   recherches web sur l'entreprise + analyse détaillée des compétences demandées.

Les fonctions ici ne touchent pas au stockage : main.py lit et enregistre les candidatures.
"""

import asyncio
import json
import re
import unicodedata
from datetime import date, datetime, timezone

from . import llm, prompts, websearch

PREP_MAX_TOKENS = 4500
MAX_SNIPPET = 300
MAX_REPLIES = 30  # échanges gardés par candidature (limite de taille d'un document Firestore)

# Statut de la candidature selon le type de réponse reçue (statuts : notsent, sent, positive, refused).
STATUS_FOR_REPLY = {"entretien": "positive", "test": "positive", "offre": "positive",
                    "demande_infos": "positive", "refus": "refused"}
CLOSED = ("refused",)
PREPARE_FOR = ("entretien", "test", "offre", "demande_infos")
STOPWORDS = {"de", "du", "des", "en", "et", "la", "le", "les", "un", "une", "h", "f", "e", "a", "au", "pour"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def _title_similarity(a: str, b: str) -> float:
    """Part des mots significatifs du poste le plus court présents dans l'autre (0 à 1)."""
    wa = {w for w in _normalize(a).split() if w not in STOPWORDS}
    wb = {w for w in _normalize(b).split() if w not in STOPWORDS}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def find_application(applications: list[dict], company: str, title: str) -> dict | None:
    """Retrouve la candidature qui correspond le mieux à l'entreprise (et au poste).

    Une candidature refusée n'est reprise que si le poste correspond aussi : une nouvelle
    invitation chez la même entreprise concerne souvent un autre poste. Si le poste est connu
    et ne correspond à aucune candidature de l'entreprise, on ne rattache qu'à une
    candidature en cours unique.
    """
    target = _normalize(company)
    if not target:
        return None
    candidates = []
    for app in applications:
        name = _normalize(app.get("company", ""))
        if not name or not (name == target or name in target or target in name):
            continue
        same_title = bool(title) and _title_similarity(title, app.get("jobTitle", "")) >= 0.5
        if app.get("status") in CLOSED and not same_title:
            continue
        score = (2 if name == target else 1) + (2 if same_title else 0) + (1 if app.get("status") not in CLOSED else 0)
        candidates.append((score, same_title, app))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, same_title, best = candidates[0]
    if title and not same_title and len(candidates) > 1:
        return None  # plusieurs candidatures en cours, aucune pour ce poste : on ne devine pas
    return best


async def analyze_reply(message: str, applications: list[dict]) -> dict:
    known = "; ".join(f"{a['company']} ({a.get('jobTitle') or '?'})" for a in applications if a.get("company"))[:1500]
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


def _next_step(info: dict) -> dict | None:
    kind = info["type_reponse"]
    if kind == "refus":
        return None
    if info["date_entretien"]:
        label = " · ".join(x for x in (info.get("heure"), info.get("format")) if x)
        return {"date": info["date_entretien"], "kind": "interview" if kind != "test" else "test", "label": label}
    if info["date_limite"]:
        return {"date": info["date_limite"], "kind": "deadline", "label": info.get("a_faire", "")}
    if info.get("a_faire"):
        return {"date": date.today().isoformat(), "kind": "todo", "label": info["a_faire"]}
    return None


def _set_status(record: dict, status: str) -> None:
    if status == record.get("status"):
        return
    record["status"] = status
    record["lastStatusChangeAt"] = now()
    if status != "notsent" and not record.get("sentAt"):
        record["sentAt"] = record["lastStatusChangeAt"]


def _merge_contact(record: dict, info: dict) -> None:
    """Complète la section contact sans écraser ce que la personne a déjà saisi."""
    found = {"name": info.get("contact_nom", ""), "position": info.get("contact_role", ""),
             "email": info.get("contact_email", "")}
    if not any(found.values()):
        return
    sections = record.setdefault("sections", [])
    contact = next((s for s in sections if s.get("kind") == "contact"), None)
    if contact is None:
        sections.append({"id": f"reply-contact-{len(sections) + 1}", "kind": "contact", "phone": "", "extra": [], **found})
        return
    for key, value in found.items():
        if value and not (contact.get(key) or "").strip():
            contact[key] = value


def new_application(info: dict) -> dict:
    """Candidature créée à partir d'une réponse dont l'entreprise n'est pas encore suivie."""
    stamp = now()
    return {
        "type": "regular", "company": info.get("entreprise") or "?", "jobTitle": info.get("poste", ""),
        "status": "sent", "sections": [], "createdAt": stamp, "lastStatusChangeAt": stamp, "sentAt": stamp,
    }


def apply_reply(record: dict, info: dict, message: str) -> dict:
    """Met à jour la candidature (copie) avec la réponse : statut, prochaine étape, contact, historique."""
    record = json.loads(json.dumps(record))  # copie profonde : l'original reste intact
    record.pop("id", None)
    status = STATUS_FOR_REPLY.get(info["type_reponse"])
    if status:
        _set_status(record, status)
    elif record.get("status") == "notsent":
        _set_status(record, "sent")
    if info["type_reponse"] == "refus" or _next_step(info):
        record["nextStep"] = _next_step(info)
    if not record.get("jobTitle") and info.get("poste"):
        record["jobTitle"] = info["poste"]
    _merge_contact(record, info)
    reply = {
        "at": now(), "type": info["type_reponse"], "summary": info.get("resume", ""), "todo": info.get("a_faire", ""),
        "date": info["date_entretien"], "time": info.get("heure", ""), "format": info.get("format", ""),
        "place": info.get("lieu_ou_lien", ""), "deadline": info["date_limite"], "situation": situation_text(info),
        "message": message,
    }
    record["replies"] = [reply, *record.get("replies", [])][:MAX_REPLIES]
    return record


# ---------- Préparation d'entretien ----------

def section(record: dict, kind: str) -> dict:
    return next((s for s in record.get("sections", []) if s.get("kind") == kind), {})


def offer_text(record: dict) -> str:
    """Texte de l'offre : texte complet enregistré, sinon les points clés."""
    raw = (section(record, "offerLink").get("rawText") or "").strip()
    if raw:
        return raw
    kp = section(record, "keyPoints")
    lines = [f"{k} : {kp[k]}" for k in ("contract", "salary", "workMode", "experience", "start") if kp.get(k)]
    for k in ("responsibilities", "requirements"):
        items = kp.get(k) or []
        if items:
            lines.append(f"{k} :\n" + "\n".join(f"- {i}" for i in items))
    return "\n".join(lines)


async def research_company(company: str) -> tuple[str, list[str]]:
    """Recherches web sur l'entreprise ; renvoie (texte pour l'IA, étapes lisibles)."""
    if not company.strip() or company == "?":
        return "", []
    queries = (
        f"{company} entreprise activité chiffres clés",
        f"{company} actualités recrutement culture avis salariés",
    )
    results = await asyncio.gather(*(websearch.search(q, max_results=5) for q in queries), return_exceptions=True)
    lines, steps, seen = [], [], set()
    for query, found in zip(queries, results):
        if isinstance(found, Exception):
            steps.append(f"{query} : {found}")
            continue
        steps.append(query)
        for r in found:
            if r["url"] in seen:
                continue
            seen.add(r["url"])
            lines.append(f"- {r['title']} ({r['url']}) : {r.get('snippet', '')[:MAX_SNIPPET]}")
    return "\n".join(lines)[: prompts.MAX_RESEARCH], steps


async def fetch_offer(record: dict) -> str:
    """Lit la page de l'offre quand aucun texte n'a été enregistré ; renvoie "" en cas d'échec."""
    url = section(record, "offerLink").get("url", "")
    if offer_text(record) or not url:
        return ""
    try:
        page = await websearch.fetch_page(url, max_chars=prompts.MAX_OFFER_TEXT)
    except websearch.WebSearchError:
        return ""
    return page.get("text", "")


async def prepare(record: dict, profile: dict, lang: str = "fr") -> tuple[str, list[str]]:
    """Génère la fiche de préparation d'entretien ; renvoie (texte Markdown, étapes de recherche)."""
    company_summary = section(record, "company").get("summary", "")
    research, steps = await research_company(record.get("company", ""))
    if company_summary:
        research = f"Résumé de l'entreprise déjà enregistré par la personne :\n{company_summary}\n\n{research}".strip()
    replies = record.get("replies") or []
    kp = section(record, "keyPoints")
    application = {
        "title": record.get("jobTitle", ""), "company": record.get("company", ""),
        "contract_type": kp.get("contract", ""), "location": kp.get("workMode", ""),
        "offer_text": offer_text(record),
    }
    text = await llm.chat(
        prompts.interview_prep_messages(profile, application, replies[0]["situation"] if replies else "", research, lang),
        temperature=0.4, max_tokens=PREP_MAX_TOKENS,
    )
    return text, steps
