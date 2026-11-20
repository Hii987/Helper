"""Entreprises à démarcher pour une candidature spontanée.

1. Recherche : l'IA traduit ce que cherche la personne en codes d'activité (NAF), puis l'API
   publique « Recherche d'entreprises » (recherche-entreprises.api.gouv.fr) liste les
   établissements actifs dans le rayon choisi autour d'un lieu géocodé par la Géoplateforme.
2. Contact : on trouve le site de l'entreprise et on y relève les adresses e-mail **publiées**
   (recrutement@, rh@, contact@…) et la page carrières. Aucune adresse n'est devinée.
3. Candidature : l'IA rédige un e-mail de candidature spontanée, que la personne envoie elle-même.
"""

import asyncio
import json
import math
import re
import unicodedata
from functools import cache
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from . import llm, prompts, websearch

GEOCODE_URL = "https://data.geopf.fr/geocodage/search"
COMPANIES_URL = "https://recherche-entreprises.api.gouv.fr/near_point"
MAX_RADIUS = 50  # km, limite de l'API
API_PAGES = 3  # pages de 25 établissements lues par page de résultats
MAX_ACTIVITIES = 6

# Tranches d'effectif salarié de l'INSEE : code → nombre minimal de salariés.
SIZE_MIN = {"00": 0, "01": 1, "02": 3, "03": 6, "11": 10, "12": 20, "21": 50, "22": 100,
            "31": 200, "32": 250, "41": 500, "42": 1000, "51": 2000, "52": 5000, "53": 10000}

# Sites qui parlent des entreprises sans être leur site officiel.
DIRECTORIES = (
    "societe.com", "pappers.fr", "pagesjaunes.fr", "infogreffe.fr", "annuaire-entreprises.data.gouv.fr",
    "verif.com", "manageo.fr", "linkedin.com", "facebook.com", "instagram.com", "indeed.", "glassdoor.",
    "welcometothejungle.com", "hellowork.com", "kompass.com", "corporama.com", "figaro", "wikipedia.org",
    "lefigaro.fr", "dnb.com", "societeinfo.com", "entreprises.lefigaro.fr", "infonet.fr", "doctrine.fr",
    "youtube.com", "x.com", "twitter.com", "google.", "mappy.com", "yelp.", "tripadvisor.",
)
CONTACT_WORDS = ("contact", "recrut", "carriere", "career", "emploi", "job", "rejoindre", "join",
                 "mentions-legales", "mentions_legales", "legal", "about", "a-propos", "equipe", "team")
CAREERS_WORDS = ("recrut", "carriere", "career", "emploi", "job", "rejoindre", "join-us", "joinus")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMAIL_JUNK = re.compile(r"\.(png|jpe?g|gif|svg|webp|css|js)$|example\.|sentry|wixpress|domain\.|email\.com$|@2x|"
                        r"u00|godaddy|cloudflare|noreply|no-reply|nepasrepondre|ne-pas-repondre", re.I)
RECRUITING = re.compile(r"recrut|rh\b|^rh|drh|career|carriere|job|emploi|talent|candidat|hr\b|^hr|stage|alternance|jobs", re.I)
GENERIC = re.compile(r"^(contact|info|infos|hello|bonjour|accueil|direction|admin|office|secretariat|agence|commercial|communication)", re.I)
MAX_PAGES = 6


@cache
def naf_labels() -> dict[str, str]:
    """Nomenclature officielle NAF rév. 2 (INSEE, via @socialgouv/codes-naf) : code → libellé."""
    return json.loads((Path(__file__).parent / "data" / "naf.json").read_text(encoding="utf-8"))


class CompanySearchError(Exception):
    """Erreur lisible renvoyée à l'utilisateur."""


# ---------- Recherche ----------

async def geocode(place: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(GEOCODE_URL, params={"q": place, "limit": 1})
    except httpx.HTTPError as exc:
        raise CompanySearchError(f"Service de géolocalisation injoignable : {exc}") from exc
    features = (resp.json().get("features") or []) if resp.status_code == 200 else []
    if not features:
        raise CompanySearchError(f"Lieu introuvable : « {place} ». Essaie une ville ou une adresse en France.")
    lon, lat = features[0]["geometry"]["coordinates"]
    return {"label": features[0]["properties"].get("label", place), "lat": lat, "lon": lon}


def keyword_candidates(what: str, limit: int = 10) -> list[str]:
    """Codes dont le libellé officiel contient un mot de la recherche (« comptable » → Activités comptables)."""
    stems = {w[:6] for w in _words(what) if len(w) >= 5}
    found = [code for code, label in naf_labels().items() if stems & {w[:6] for w in _words(label)}]
    return found[:limit]


async def choose_activities(what: str) -> list[dict]:
    """Codes NAF (rév. 2) pertinents : l'IA propose, puis trie en voyant les libellés officiels."""
    labels = naf_labels()
    raw = await llm.chat(prompts.naf_messages(what), temperature=0.1, json_mode=True)
    try:
        items = json.loads(raw).get("activites") or []
    except (ValueError, AttributeError):
        items = []
    proposed = [str(i.get("code", "")).strip().upper() for i in items if isinstance(i, dict)]
    candidates = list(dict.fromkeys(c for c in proposed + keyword_candidates(what) if c in labels))
    if not candidates:
        raise CompanySearchError("Je n'ai pas trouvé de secteur d'activité pour cette recherche : précise le métier ou le secteur.")
    raw = await llm.chat(prompts.naf_rank_messages(what, [(c, labels[c]) for c in candidates]),
                         temperature=0, json_mode=True)
    try:
        ranked = [str(c).strip().upper() for c in json.loads(raw).get("codes") or []]
    except (ValueError, AttributeError):
        ranked = []
    chosen = [c for c in dict.fromkeys(ranked) if c in candidates] or candidates
    return [{"code": c, "label": labels[c]} for c in chosen[:MAX_ACTIVITIES]]


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _size(code: str | None) -> int | None:
    return SIZE_MIN.get(code or "")


def to_result(company: dict, center: dict, radius: float, min_size: int) -> dict | None:
    """Un résultat par entreprise : son établissement actif le plus proche, s'il convient."""
    if company.get("etat_administratif") != "A" or company.get("statut_diffusion") == "P":
        return None
    best = None
    for e in company.get("matching_etablissements") or []:
        if e.get("etat_administratif") != "A" or not e.get("latitude"):
            continue
        d = distance_km(center["lat"], center["lon"], float(e["latitude"]), float(e["longitude"]))
        if d <= radius and (best is None or d < best[0]):
            best = (d, e)
    if best is None:
        return None
    d, e = best
    size = _size(e.get("tranche_effectif_salarie"))
    company_size = _size(company.get("tranche_effectif_salarie"))
    employs = company.get("caractere_employeur") == "O" or (company_size or 0) > 0
    if min_size and not ((company_size or 0) >= min_size or (size or 0) >= min_size):
        return None
    if min_size == 1 and not employs:
        return None
    signs = [x for x in (e.get("liste_enseignes") or []) if x]
    name = (e.get("nom_commercial") or (signs[0] if signs else "") or company.get("nom_complet") or "").strip()
    name = re.sub(r"^(.+?) \(\1\)$", r"\1", name, flags=re.I)  # « TRUSTTEAM (TRUSTTEAM) »
    return {
        "siren": company.get("siren", ""),
        "name": name.title() if name.isupper() else name,
        "legalName": company.get("nom_complet", ""),
        "activity": company.get("activite_principale", ""),
        "activityLabel": naf_labels().get(company.get("activite_principale", ""), ""),
        "sizeCode": company.get("tranche_effectif_salarie") or "",
        "siteSizeCode": e.get("tranche_effectif_salarie") or "",
        "address": e.get("adresse", ""),
        "city": e.get("libelle_commune", ""),
        "distanceKm": round(d, 1),
        "headOffice": bool(e.get("est_siege")),
    }


async def _page(client: httpx.AsyncClient, center: dict, radius: float, codes: str, page: int) -> dict:
    params = {"lat": center["lat"], "long": center["lon"], "radius": radius, "activite_principale": codes,
              "per_page": 25, "page": page}
    resp = await client.get(COMPANIES_URL, params=params)
    if resp.status_code == 429:
        await asyncio.sleep(1)
        resp = await client.get(COMPANIES_URL, params=params)
    if resp.status_code != 200:
        raise CompanySearchError(f"L'annuaire des entreprises a répondu {resp.status_code}.")
    return resp.json()


async def search(center: dict, activities: list[dict], radius: float, min_size: int, page: int = 1) -> dict:
    radius = max(1, min(float(radius), MAX_RADIUS))
    codes = ",".join(a["code"] for a in activities)
    first = (page - 1) * API_PAGES + 1
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            pages = []
            for n in range(first, first + API_PAGES):  # l'API limite le débit : pages lues l'une après l'autre
                data = await _page(client, center, radius, codes, n)
                pages.append(data)
                if n >= (data.get("total_pages") or 0):
                    break
    except httpx.HTTPError as exc:
        raise CompanySearchError(f"Annuaire des entreprises injoignable : {exc}") from exc
    seen, results = set(), []
    for data in pages:
        for company in data.get("results") or []:
            result = to_result(company, center, radius, min_size)
            if result and result["siren"] not in seen:
                seen.add(result["siren"])
                results.append(result)
    rank = {a["code"]: i for i, a in enumerate(activities)}  # secteurs les plus pertinents d'abord
    results.sort(key=lambda r: (rank.get(r["activity"], len(rank)), r["distanceKm"]))
    total_pages = pages[0].get("total_pages") or 0 if pages else 0
    return {"results": results, "page": page, "hasMore": first + API_PAGES - 1 < total_pages,
            "scanned": sum(len(d.get("results") or []) for d in pages), "totalInRadius": pages[0].get("total_results", 0) if pages else 0}


# ---------- Contact : site officiel et e-mails publiés ----------

def _domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", _ascii(text)) if len(w) > 2}


def pick_website(results: list[dict], name: str) -> str:
    """Premier résultat qui n'est pas un annuaire et dont l'adresse ou le titre évoque l'entreprise."""
    wanted = _words(name) - {"sas", "sarl", "groupe", "group", "france", "societe", "the", "les", "des"}
    for r in results:
        url, domain = r.get("url", ""), _domain(r.get("url", ""))
        if not domain or any(d in domain for d in DIRECTORIES):
            continue
        haystack = _words(domain.replace(".", " ") + " " + r.get("title", ""))
        if not wanted or wanted & haystack:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.hostname}/"
    return ""


def _deobfuscate(text: str) -> str:
    text = re.sub(r"\s*[\[(\{]\s*(at|arobase)\s*[\])\}]\s*", "@", text, flags=re.I)
    return re.sub(r"\s*[\[(\{]\s*(dot|point)\s*[\])\}]\s*", ".", text, flags=re.I)


def extract_emails(page: str) -> set[str]:
    text = _deobfuscate(re.sub(r"&#64;|&#x40;|%40", "@", page, flags=re.I))
    found = {m.group(0).strip(".").lower() for m in EMAIL.finditer(text)}
    return {e for e in found if not EMAIL_JUNK.search(e) and len(e) < 80}


def contact_links(base: str, page: str) -> list[str]:
    """Liens internes vers les pages contact, recrutement, mentions légales…"""
    links = []
    for href in re.findall(r'href=["\']([^"\'#]+)', page, re.I):
        url = urljoin(base, href)
        if _domain(url) != _domain(base) or not url.startswith("http"):
            continue
        path = _ascii(urlparse(url).path)
        if any(w in path for w in CONTACT_WORDS) and url not in links:
            links.append(url)
    return links


def rank_emails(emails: set[str], domain: str) -> list[dict]:
    def kind(e: str) -> str:
        local = e.split("@")[0]
        if RECRUITING.search(local):
            return "recruiting"
        if GENERIC.search(local):
            return "generic"
        return "named" if re.search(r"[a-z]\.[a-z]", local) else "other"

    order = {"recruiting": 0, "generic": 1, "other": 2, "named": 3}
    ranked = [{"email": e, "kind": kind(e), "sameDomain": e.split("@")[1].endswith(domain)} for e in emails]
    ranked.sort(key=lambda x: (not x["sameDomain"], order[x["kind"]], x["email"]))
    return ranked[:8]


async def find_contact(name: str, city: str) -> dict:
    """Site officiel, e-mails publiés et page carrières d'une entreprise."""
    try:
        results = await websearch.search(f"{name} {city} site officiel", max_results=8)
    except websearch.WebSearchError as exc:
        raise CompanySearchError(str(exc)) from exc
    website = pick_website(results, name)
    if not website:
        return {"website": "", "emails": [], "careersUrl": "", "description": "", "pages": 0}
    domain = _domain(website)
    emails: set[str] = set()
    description, careers, visited = "", "", 0
    try:
        home_url, home = await websearch.fetch_html(website, timeout=12)
    except websearch.WebSearchError:
        return {"website": website, "emails": [], "careersUrl": "", "description": "", "pages": 0}
    visited = 1
    emails |= extract_emails(home)
    description = websearch.html_to_text(home)[1][:1200]
    links = contact_links(home_url, home)
    careers = next((u for u in links if any(w in _ascii(urlparse(u).path) for w in CAREERS_WORDS)), "")
    pages = await asyncio.gather(*(websearch.fetch_html(u, timeout=10) for u in links[:MAX_PAGES - 1]), return_exceptions=True)
    for found in pages:
        if not isinstance(found, Exception):
            visited += 1
            emails |= extract_emails(found[1])
    # Une adresse d'un autre domaine n'est gardée que s'il n'y a rien sur le domaine du site.
    ranked = rank_emails(emails, domain)
    if any(e["sameDomain"] for e in ranked):
        ranked = [e for e in ranked if e["sameDomain"]]
    return {"website": website, "emails": ranked, "careersUrl": careers, "description": description, "pages": visited}


# ---------- Candidature spontanée ----------

async def write_application(profile: dict, company: dict, lang: str = "fr") -> dict:
    raw = await llm.chat(prompts.spontaneous_messages(profile, company, lang), temperature=0.5, json_mode=True)
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise llm.LLMError("La réponse de l'IA est illisible, réessaie.") from exc
    subject, body = str(data.get("objet") or "").strip(), str(data.get("corps") or "").strip()
    if not body:
        raise llm.LLMError("L'IA n'a pas rédigé de message, réessaie.")
    return {"subject": subject, "body": body}
